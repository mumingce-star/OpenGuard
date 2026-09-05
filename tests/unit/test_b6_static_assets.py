"""Static declaration evidence is bounded to exact references and source files."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.detectors import detect_ai_assets
from app.domain.models import AIAssetType, VerificationStatus

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)
MODEL = "https://huggingface.co/Qwen/Qwen3-0.6B"
DATASET = "https://huggingface.co/datasets/example/research"


def test_qwen_reference_is_pending_and_bound_to_entire_utf8_file():
    text = '模型引用\nmodel = "' + MODEL + '"; api_key="neighbor-private-value"\n'
    assets, evidence = detect_ai_assets({"src/model.py": text}, observed_at=NOW)
    assert len(assets) == len(evidence) == 1
    asset, item = assets[0], evidence[0]
    assert asset.asset_type == AIAssetType.MODEL
    assert asset.name == "Qwen/Qwen3-0.6B"
    assert asset.source_url == MODEL
    assert asset.authorization_status == VerificationStatus.PENDING
    assert asset.license_expression_id is None
    assert asset.confidence == 0.6
    assert asset.evidence_ids == [item.id]
    assert item.excerpt == MODEL
    assert item.content_hash.value == hashlib.sha256(text.encode()).hexdigest()
    assert item.start_line == item.end_line == 2
    assert item.verification_status == VerificationStatus.PENDING
    assert item.producer.version == "0.1.1"
    assert "neighbor-private-value" not in item.model_dump_json()


def test_dataset_is_not_also_model():
    assets, evidence = detect_ai_assets({"README.md": DATASET}, observed_at=NOW)
    assert len(assets) == len(evidence) == 1
    assert assets[0].asset_type == AIAssetType.DATASET
    assert assets[0].name == "example/research"


def test_duplicate_same_line_is_one_evidence_and_different_line_is_separate():
    assets, evidence = detect_ai_assets({"README.md": f"{MODEL} {MODEL}\n{MODEL}"}, observed_at=NOW)
    assert len(assets) == 1
    assert len(evidence) == len(assets[0].evidence_ids) == 2
    assert {item.start_line for item in evidence} == {1, 2}
    assert len({item.content_hash.value for item in evidence}) == 1


def test_changed_content_changes_evidence_identity_but_not_asset_identity():
    before = detect_ai_assets({"README.md": MODEL}, observed_at=NOW)
    after = detect_ai_assets({"README.md": MODEL + "\nchanged"}, observed_at=NOW)
    assert before[0][0].id == after[0][0].id
    assert before[1][0].id != after[1][0].id
    assert before == detect_ai_assets({"README.md": MODEL}, observed_at=NOW)


@pytest.mark.parametrize("reference", [
    "http://huggingface.co/Qwen/Qwen3-0.6B",
    "https://huggingface.co.evil.example/Qwen/Qwen3-0.6B",
    "https://user:secret@huggingface.co/Qwen/Qwen3-0.6B",
    MODEL + "?token=secret", MODEL + "#private", MODEL + "/resolve/main/config.json",
    MODEL + "%2Fsecret", MODEL + "@evil.example", MODEL + "\\secret",
    "evilhttps://huggingface.co/Qwen/Qwen3-0.6B",
    "https://huggingface.co/docs/transformers", "https://huggingface.co/spaces/demo",
    "https://huggingface.co/settings/tokens", "https://huggingface.co/datasets/research",
    "https://huggingface.co/Qwen/..", "https://huggingface.co/api/models",
])
def test_ambiguous_or_non_resource_urls_are_not_partially_recognized(reference):
    assert detect_ai_assets({"README.md": reference}, observed_at=NOW) == ([], [])


@pytest.mark.parametrize("locator", ["/tmp/model.txt", "../model.txt", "a/../model.txt", "a\\model.txt", "C:/model.txt", "a//b", "./b", "a\x00b"])
def test_rejects_non_relative_file_locators_even_without_reference(locator):
    with pytest.raises(ValueError, match="relative locators"):
        detect_ai_assets({locator: "unrelated"}, observed_at=NOW)


@pytest.mark.parametrize("timestamp", [datetime(2026, 9, 5), datetime(2026, 9, 5, tzinfo=timezone(timedelta(hours=8)))])
def test_rejects_non_utc_timestamp_even_without_matches(timestamp):
    with pytest.raises(ValueError, match="UTC"):
        detect_ai_assets({}, observed_at=timestamp)


def test_other_existing_patterns_keep_only_the_matched_reference():
    assets, evidence = detect_ai_assets({"client.py": 'secret="hidden"; openai.responses; anthropic.messages; google.genai'}, observed_at=NOW)
    assert len(assets) == len(evidence) == 3
    assert {item.asset_type for item in assets} == {AIAssetType.API}
    assert {item.excerpt for item in evidence} == {"openai.responses", "anthropic.messages", "google.genai"}
    assert all(item.source_url is None for item in assets)


def test_existing_modelscope_reference():
    assets, _ = detect_ai_assets({"README.md": "https://modelscope.cn/models/Qwen/Qwen3-0.6B"}, observed_at=NOW)
    assert len(assets) == 1
    assert assets[0].provider == "modelscope"
