"""R1B-A: four frozen targets plus FN-07 natural coverage; public entry only."""
import hashlib
import json
from datetime import datetime, timezone

import pytest

from app.detectors import detect_ai_assets

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)
QWEN = 'Qwen/Qwen3-Next-80B-A3B-Thinking'


@pytest.mark.parametrize('source,provider,name,line', [
    (f'from smolagents import InferenceClientModel\nmodel = InferenceClientModel(\n model_id="{QWEN}",\n)\n', 'huggingface', QWEN, 3),
    (f'from smolagents import TransformersModel\nmodel = TransformersModel(\n model_id="{QWEN}",\n)\n', 'huggingface', QWEN, 3),
    ('import litellm\nresponse = await litellm.anthropic.messages.acreate(\n model="anthropic/claude-3-haiku-20240307",\n)\n', 'anthropic', 'anthropic/claude-3-haiku-20240307', 3),
    ('from litellm.google_genai import generate_content\nresponse = generate_content(\n model="gemini-pro",\n)\n', 'google', 'gemini-pro', 3),
    ('from smolagents import InferenceClientModel\nmodel = InferenceClientModel(\n model_id="deepseek-ai/DeepSeek-R1",\n provider="together",\n)\n', 'huggingface', 'deepseek-ai/DeepSeek-R1', 3),
], ids=['tier-a-tools','tier-a-readme','tier-a-anthropic','tier-a-google','fn07-natural-coverage'])
def test_frozen_targets(source, provider, name, line):
    assets, evidence = detect_ai_assets({'example.py': source}, observed_at=NOW)
    models = [a for a in assets if a.asset_type.value == 'model']
    assert len(models) == 1
    a = models[0]
    assert (a.provider, a.name, a.source_url) == (provider, name, None)
    assert a.authorization_status.value == 'pending' and a.license_expression_id is None
    assert [v.value for v in a.detected_by] == ['ast'] and a.confidence == 0.6
    refs = [e for e in evidence if e.id in a.evidence_ids]
    assert len(refs) == 1
    e = refs[0]
    assert e.detected_by.value == 'ast' and e.verification_status.value == 'pending'
    assert (e.producer.name, e.producer.version) == ('openguard-static-ai-detector', '0.2.0')
    assert e.locator == 'example.py' and e.start_line == e.end_line == line
    assert e.excerpt == name
    assert e.content_hash.value == hashlib.sha256(source.encode()).hexdigest()


@pytest.mark.parametrize('source', [
    'model="user"', 'model="invoice"', 'model="v1"', 'model_id="123"',
    'SomeClass(model_id="deepseek-ai/DeepSeek-R1")',
    'generate_content(model="gemini-pro")', '{"model":"gemini-pro"}',
    'path="org/model"', 'package="@scope/package"', 'repo="owner/repo"',
    'from smolagents import *\nInferenceClientModel(model_id="org/model")',
    'from other import InferenceClientModel\nInferenceClientModel(model_id="org/model")',
    'def InferenceClientModel(**kwargs): pass\nInferenceClientModel(model_id="org/model")',
    'from smolagents import InferenceClientModel\nInferenceClientModel = other\nInferenceClientModel(model_id="org/model")',
    'from smolagents import InferenceClientModel\ndef f(InferenceClientModel):\n return InferenceClientModel(model_id="org/model")',
    'from smolagents import OpenAIModel, LiteLLMModel\nOpenAIModel(model_id="org/model")\nLiteLLMModel(model_id="org/model")',
    'from datasets import load_dataset\nload_dataset("org/model")',
    '_rule("org/model")',
])
def test_non_ai_or_unapproved_contexts(source):
    assets, _ = detect_ai_assets({'example.py': source}, observed_at=NOW)
    assert not [a for a in assets if a.asset_type.value == 'model']


@pytest.mark.parametrize('value', ['os.environ["MODEL_ID"]','config.model','f"{org}/{name}"','get_model()', '"org/" + "model"'])
def test_dynamic_values_are_not_specific_assets(value):
    source = 'from smolagents import InferenceClientModel\nInferenceClientModel(model_id=' + value + ')'
    assert detect_ai_assets({'example.py': source}, observed_at=NOW) == ([], [])


@pytest.mark.parametrize('lang', ['python','py','python3','python showLineNumbers title="Example"'])
def test_markdown_language_and_original_line(lang):
    text = '# Intro\n\n```' + lang + '\nfrom smolagents import InferenceClientModel\nInferenceClientModel(model_id="org/model")\n```\n'
    assets, evidence = detect_ai_assets({'docs/usage.md': text}, observed_at=NOW)
    assert len(assets) == len(evidence) == 1
    assert evidence[0].locator == 'docs/usage.md'
    assert evidence[0].start_line == evidence[0].end_line == 5
    assert evidence[0].content_hash.value == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize('lang', ['', 'text','shell','json','yaml'])
def test_non_python_fences(lang):
    text = '```' + lang + '\nfrom smolagents import InferenceClientModel\nInferenceClientModel(model_id="org/model")\n```'
    assert detect_ai_assets({'README.md': text}, observed_at=NOW) == ([], [])


@pytest.mark.parametrize('locator,text', [('x.json','{"model":"claude-3-7-sonnet-latest"}'),('README.md','model_id="Qwen/Qwen3"'),('x.txt','from smolagents import InferenceClientModel\nInferenceClientModel(model_id="org/model")')])
def test_unsupported_files_and_prose(locator,text):
    assert detect_ai_assets({locator:text}, observed_at=NOW) == ([], [])


@pytest.mark.parametrize('locator,source', [('broken.py','def broken(:\n'), ('README.md','```python\ndef broken(:\n```\n')])
def test_syntax_failure_keeps_url_detection(locator, source):
    text = source + '\n# https://huggingface.co/org/model\n'
    assets,evidence = detect_ai_assets({locator:text}, observed_at=NOW)
    assert len(assets) == len(evidence) == 1
    assert assets[0].source_url == 'https://huggingface.co/org/model'


@pytest.mark.parametrize('source', [
    'from smolagents import InferenceClientModel as ICM\nICM(model_id="org/unseen")',
    'import smolagents as sm\nsm.TransformersModel(model_id="org/unseen")',
    'import litellm as ll\nll.anthropic.messages.acreate(model="anthropic/unseen")',
    'from litellm.google_genai import generate_content as gc\ngc(model="unseen")',
])
def test_import_aliases(source):
    assets,_ = detect_ai_assets({'x.py':source}, observed_at=NOW)
    assert len([a for a in assets if a.asset_type.value=='model'])==1


@pytest.mark.parametrize('fn', ['generate_content','agenerate_content','generate_content_stream','agenerate_content_stream'])
def test_google_approved_functions_in_async_scope(fn):
    source=f'from litellm.google_genai import {fn}\nasync def main():\n return {fn}(model="unseen-model")\n'
    assets,_=detect_ai_assets({'x.py':source},observed_at=NOW)
    assert any(a.asset_type.value=='model' and a.name=='unseen-model' for a in assets)


def test_runtime_provider_does_not_change_identity_and_secrets_stay_out():
    source='from smolagents import InferenceClientModel\nInferenceClientModel(model_id="deepseek-ai/DeepSeek-R1", provider="together", api_key="SHOULD_NOT_APPEAR")\nInferenceClientModel(model_id="deepseek-ai/DeepSeek-R1")\n'
    assets,evidence=detect_ai_assets({'x.py':source},observed_at=NOW)
    assert len(assets)==1 and len(evidence)==2
    a=assets[0]
    assert a.provider=='huggingface' and a.source_url is None
    assert a.authorization_status.value=='pending' and a.license_expression_id is None
    assert set(a.evidence_ids)=={e.id for e in evidence}
    assert 'SHOULD_NOT_APPEAR' not in json.dumps([x.model_dump(mode='json') for x in assets+evidence])


def test_url_and_ast_merge_preserves_static_identity_and_source():
    text='from smolagents import InferenceClientModel\n# https://huggingface.co/org/model\nInferenceClientModel(model_id="org/model")\n'
    assets,evidence=detect_ai_assets({'x.py':text},observed_at=NOW)
    assert len(assets)==1 and len(evidence)==2
    assert assets[0].source_url=='https://huggingface.co/org/model'
    assert {m.value for m in assets[0].detected_by}=={'static_pattern','ast'}
    # Frozen 0.1.2 URL identity formula, independent of the implementation helper.
    import uuid
    digest=hashlib.sha256(text.encode()).hexdigest()
    old_id='evd_'+str(uuid.uuid5(uuid.UUID('e6047e12-66d2-5ebb-b78a-756e0ee05601'),'|'.join(['x.py',digest,'2','model','huggingface','org/model','https://huggingface.co/org/model'])))
    assert next(e.id for e in evidence if e.detected_by.value=='static_pattern')==old_id
    assert set(assets[0].evidence_ids)=={e.id for e in evidence}


@pytest.mark.parametrize('ast_first', [True, False])
def test_cross_file_merge_in_both_orders(ast_first):
    source='from smolagents import InferenceClientModel\nInferenceClientModel(model_id="org/model")'
    files={'a.py':source,'z.md':'https://huggingface.co/org/model'} if ast_first else {'z.py':source,'a.md':'https://huggingface.co/org/model'}
    assets,evidence=detect_ai_assets(files,observed_at=NOW)
    assert len(assets)==1 and len(evidence)==2
    assert {x.value for x in assets[0].detected_by}=={'ast','static_pattern'}
    assert assets[0].source_url=='https://huggingface.co/org/model'
    assert set(assets[0].evidence_ids)=={e.id for e in evidence}


@pytest.mark.parametrize('source', [
    'InferenceClientModel(model_id="org/model")\nfrom smolagents import InferenceClientModel',
    'import smolagents as sm\nsm.InferenceClientModel=other\nsm.InferenceClientModel(model_id="org/model")',
    'from .smolagents import InferenceClientModel\nInferenceClientModel(model_id="org/model")',
])
def test_invalid_bindings_do_not_create_models(source):
    assets,_=detect_ai_assets({'x.py':source},observed_at=NOW)
    assert not any(a.asset_type.value=='model' for a in assets)


def test_import_does_not_cross_markdown_blocks():
    text='```py\nfrom smolagents import InferenceClientModel\n```\n```py\nInferenceClientModel(model_id="org/model")\n```'
    assert detect_ai_assets({'x.md':text},observed_at=NOW)==([],[])
