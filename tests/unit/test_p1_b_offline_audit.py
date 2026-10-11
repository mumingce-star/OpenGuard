"""P1 审计不能升级机器裁决、错绑原证据或读取 holdout 个案。"""
import copy
from pathlib import Path

import pytest

from benchmarks.p1_b_offline_audit import blind_source_packet, fixture_chain, load, profile_sources, sha, verify_case


def case():
    return {"split": "dev", "locator": "example.py", "line": 1,
            "evidence_sha256": sha(b"model = 'a/b'\n"), "adjudication": None}


def test_verified_source_is_not_a_confirmed_detector_error_or_gold():
    result = verify_case(case(), {"example.py": "model = 'a/b'\n"})
    assert result["triage_state"] == "待真人裁决"
    assert result["confirmed_detector_error"] is False
    assert result["human_adjudication"] is None


@pytest.mark.parametrize("field,value,error", [
    ("split", "holdout", "holdout_case_forbidden"),
    ("evidence_sha256", "0" * 64, "source_evidence_hash_mismatch"),
    ("line", 2, "source_line_mismatch"),
    ("line", True, "source_line_mismatch"),
])
def test_wrong_binding_and_holdout_fail_closed(field, value, error):
    modified = copy.deepcopy(case())
    modified[field] = value
    with pytest.raises(ValueError, match=error):
        verify_case(modified, {"example.py": "model = 'a/b'\n"})


def test_unreadable_source_remains_unjudgeable():
    assert verify_case(case(), {})["triage_state"] == "无法判断"


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_audit_rejects_ambiguous_json(tmp_path, raw):
    target = tmp_path / "input.json"
    target.write_bytes(raw)
    with pytest.raises(ValueError):
        load(target)


def test_fixed_fact_chain_does_not_invent_a_receipts():
    result = fixture_chain(Path.cwd())
    assert (result["v2_findings"], result["v2_obligations"], result["v3_facts"]) == (17, 0, 31)
    assert result["a_receipt_received"] is False
    assert len(result["rows"]) == 39
    assert all(row["a_terminal"] is None and row["draft_report"] is None for row in result["rows"])


def test_worktree_hash_does_not_prove_declared_git_revision():
    result = fixture_chain(Path.cwd())
    # 当前冻结包的已确认缺陷：不能用工作树字节一致替代 Git 对象一致。
    source = next(item for item in result["git_source_checks"] if item["path"] == "frontend/package.json")
    assert source["state"] == "mismatch"
    assert source["actual_sha256"] != source["source_file_sha256"]
    assert result["source_binding_accepted"] is False
    assert len(result["source_binding_affected_evidence"]) == 8
    assert sum(row.get("source_binding_state") == "mismatch" for row in result["rows"]) == 8


def test_offline_profile_bytes_are_not_live_attestation_or_independent_receipt():
    records = profile_sources(Path.cwd())
    assert len(records) == 28
    assert all(item["upstream_response_sha256"] is None for item in records)
    assert all(item["independent_state"] == "待签收" for item in records)


def test_blind_packet_excludes_machine_answers_and_cannot_claim_gold():
    source = {**case(), "sample_id": "sample", "source_repository": "https://github.com/example/repo.git",
              "commit_sha": "a" * 40, "input_sha256": "b" * 64,
              "machine_kind": "FP", "name": "answer", "adjudication": "previous_answer"}
    result = blind_source_packet([source, source])
    assert len(result["records"]) == 1
    assert result["formal_gold"] is False and result["reviewer_receipt"] is None
    assert not {"split", "machine_kind", "name", "adjudication", "line"} & result["records"][0].keys()


def test_blind_packet_refuses_old_holdout():
    with pytest.raises(ValueError, match="holdout_case_forbidden"):
        blind_source_packet([{"split": "holdout"}])
