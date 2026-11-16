"""Missing joint checks over published real receipts, plus synthetic tamper negatives."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from app.p2.contract import digest, strict_json

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("p2b_receipt_closure", ROOT / "tests/fixtures/p2b/verify_receipt_closure.py")
closure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closure)


def inputs():
    return [strict_json((ROOT / "tests/fixtures/p2b" / name).read_bytes()) for name in
            ("three-scan-readback.json", "real-source-index.json", "frontend-handoff-draft.json")]


def test_published_receipts_match_dtos_schema_hashes_paths_and_export():
    result = closure.verify(*inputs())
    published = strict_json((ROOT / "docs/p2/p2b-evidence-closure.json").read_bytes())
    assert result == published
    assert result["overall"] == "PARTIAL"
    assert not result["express_rule_tuning"]
    for row in result["cases"]:
        assert row["old_formal_report_readback"] is None
        assert row["full_assessment_readback"] is None
        assert row["suggestions_added"] == row["suggestions_removed"] == row["suggestions_updated"] == []


@pytest.mark.parametrize("field,value,error", [
    ("result_sha256", "0" * 64, "result_digest"),
    ("result_id", "p2res_wrong", "result_digest"),
    ("publication_status", "license_verified", "publication_status"),
    ("data_scope", "OWNER", "result_binding"),
])
def test_tampered_real_result_is_refused(field, value, error):
    args = deepcopy(inputs())
    args[0]["cases"][0]["p2"]["before"][field] = value
    with pytest.raises(ValueError, match=error):
        closure.verify(*args)


@pytest.mark.parametrize("field", ["before_get_path", "after_get_path", "material_get_path", "summary_get_path"])
def test_exact_get_cannot_select_latest_or_other_version(field):
    args = deepcopy(inputs())
    args[0]["cases"][0]["p2"][field] = "/api/v1/latest"
    with pytest.raises(ValueError, match="get_path"):
        closure.verify(*args)


def test_rehashed_result_cannot_change_manifest_basis():
    args = deepcopy(inputs())
    result = args[0]["cases"][0]["p2"]["before"]
    result["resources"][0]["evidence_source_hashes"] = {}
    result["result_sha256"] = digest({k: v for k, v in result.items() if k != "result_sha256"})
    with pytest.raises(ValueError, match="result_evidence_hashes"):
        closure.verify(*args)


def test_summary_cannot_replace_old_formal_report_or_other_revision():
    args = deepcopy(inputs())
    args[0]["cases"][2]["p2"]["summary"]["result_revision"] = 1
    with pytest.raises(ValueError, match="summary_result_binding"):
        closure.verify(*args)


def test_controlled_archive_hash_cannot_be_replaced():
    args = deepcopy(inputs())
    args[0]["cases"][0]["archive_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="controlled_input_digest"):
        closure.verify(*args)


def test_frontend_draft_cannot_relabel_unknown_before_as_pending():
    args = deepcopy(inputs())
    args[2]["cases"][0]["before"]["candidate_state"] = "pending"
    with pytest.raises(ValueError, match="draft_before_state"):
        closure.verify(*args)
