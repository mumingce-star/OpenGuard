"""B02-A: explicit model, dataset, API and configuration coverage contract."""

from datetime import datetime, timezone

import pytest

from app.detectors import detect_ai_assets


NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def _labels(files: dict[str, str]):
    assets, evidence = detect_ai_assets(files, observed_at=NOW)
    return {(item.asset_type.value, item.provider, item.name) for item in assets}, evidence


def test_explicit_runtime_sdk_calls_cover_models_datasets_and_apis_without_secret_evidence():
    files = {
        "runtime.py": """from transformers import AutoModel\nfrom datasets import load_dataset\nfrom openai import OpenAI\nfrom anthropic import Anthropic\nfrom google import genai\nimport cohere\nfrom mistralai import Mistral\nAutoModel.from_pretrained('acme/encoder')\nload_dataset('acme/corpus')\nOpenAI(api_key='never-export-this')\nAnthropic(api_key='never-export-this')\ngenai.Client(api_key='never-export-this')\ncohere.Client('never-export-this')\nMistral(api_key='never-export-this')\n""",
    }
    labels, evidence = _labels(files)
    assert labels == {
        ("model", "huggingface", "acme/encoder"),
        ("dataset", "huggingface", "acme/corpus"),
        *( ("api", provider, provider) for provider in ("openai", "anthropic", "google", "cohere", "mistral") ),
    }
    rendered = "\n".join(item.excerpt for item in evidence)
    assert "never-export-this" not in rendered
    assert {item.detected_by.value for item in evidence} == {"ast"}


def test_explicit_config_recognizes_typed_assets_and_known_service_endpoints_only():
    labels, evidence = _labels({
        "resources.toml": "model_name = 'acme/toml-model'\ndataset_id = 'acme/toml-data'\nbase_url = 'https://api.openai.com/v1/'\n",
        "resources.json": '{"nested":{"model_id":"acme/json-model","dataset_path":"acme/json-data","anthropic_base_url":"https://api.anthropic.com"}}',
        "resources.yaml": "model: 'acme/yaml-model'\ndataset: 'acme/yaml-data'\ngoogle_api_base: 'https://generativelanguage.googleapis.com'\n",
    })
    assert labels == {
        ("model", "huggingface", "acme/toml-model"), ("dataset", "huggingface", "acme/toml-data"),
        ("model", "huggingface", "acme/json-model"), ("dataset", "huggingface", "acme/json-data"),
        ("model", "huggingface", "acme/yaml-model"), ("dataset", "huggingface", "acme/yaml-data"),
        ("api", "openai", "openai"), ("api", "anthropic", "anthropic"), ("api", "google", "google"),
    }
    assert {item.detected_by.value for item in evidence} == {"manifest_parser"}
    assert all(item.kind.value == "manifest_field" for item in evidence)


@pytest.mark.parametrize("source", [
    "from openai import OpenAI\nOpenAI(api_key=key)\n",
    "base_url: 'https://evil.example/v1'\n",
    '{"api_key":"never-export-this","endpoint":"https://evil.example"}',
    "from cohere import Client\nClient(dynamic_key)\n",
])
def test_dynamic_or_unrecognized_api_configuration_does_not_become_a_service_claim(source: str):
    locator = "config.yaml" if source.startswith("base_url") else ("config.json" if source.startswith("{") else "runtime.py")
    labels, evidence = _labels({locator: source})
    if "OpenAI" in source or "Client(dynamic_key)" in source:
        assert labels in ({("api", "openai", "openai")}, {("api", "cohere", "cohere")})
        assert all("key" not in item.excerpt.lower() for item in evidence)
    else:
        assert labels == set() and evidence == []
