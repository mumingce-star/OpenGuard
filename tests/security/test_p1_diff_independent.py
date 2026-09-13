"""Independent A03 gates for fact fidelity, provenance, and read-only stability."""
import copy
import hashlib
import json
import sys
from pathlib import Path

# Reuse isolated HTTP fixtures; standalone security runs need the unit helpers.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from uuid import UUID

import pytest

from test_p1_contract_schema import EXAMPLES, validator
from test_p1_diff_api import assessment, component, comps, diff, snapshot
from test_p1_history_api import SAMPLE, env


def _license(number, expression, *, verification="pending"):
    value = copy.deepcopy(SAMPLE["licenses"][0])
    value.update(
        id="lic_" + str(UUID(int=number)),
        expression=expression,
        normalized_ids=[expression],
        verification_status=verification,
    )
    return value


def _component_with_license(number, version, license_id, name):
    value = component(number, version=version, name=name)
    value["license_expression_id"] = license_id
    return value


def test_multiple_resource_license_observations_remain_separate_and_traceable(env):
    before_licenses = [_license(101, "MIT"), _license(102, "Apache-2.0")]
    after_licenses = [_license(201, "BSD-3-Clause"), _license(202, "GPL-3.0-only")]

    def facts(licenses, first_id, second_id, first_number, second_number):
        def mutate(payload):
            payload["licenses"] = licenses
            payload["components"] = [
                _component_with_license(first_number, "1.0", first_id, "alpha"),
                _component_with_license(second_number, "2.0", second_id, "beta"),
            ]
        return mutate

    base = snapshot(env, 1, facts(before_licenses, before_licenses[0]["id"], before_licenses[1]["id"], 1, 2))
    target = snapshot(env, 2, facts(after_licenses, after_licenses[0]["id"], after_licenses[1]["id"], 3, 4))
    changes = diff(env, base, target)["license_observation_changes"]

    expression_changes = [row for row in changes if row["path"].endswith("/expression")]
    assert {(row["before"], row["after"]) for row in expression_changes} == {
        ("MIT", "BSD-3-Clause"),
        ("Apache-2.0", "GPL-3.0-only"),
    }
    assert {tuple(row["source_ids_before"]) for row in expression_changes} == {
        (before_licenses[0]["id"],),
        (before_licenses[1]["id"],),
    }
    assert {tuple(row["source_ids_after"]) for row in expression_changes} == {
        (after_licenses[0]["id"],),
        (after_licenses[1]["id"],),
    }
    for row in expression_changes:
        assert row["evidence_refs"]
        for ref in row["evidence_refs"]:
            run = base if ref["scan_id"] == base.id else target
            assert ref["evidence_id"] in {item.id for item in run.evidence}


def test_unbound_root_license_never_propagates_to_resource_changes(env):
    base = snapshot(env, 1, lambda payload: payload.update(licenses=[_license(101, "MIT")]))
    target = snapshot(env, 2, lambda payload: payload.update(licenses=[_license(201, "GPL-3.0-only")]))
    result = diff(env, base, target)
    assert result["resources"] == []
    changes = result["license_observation_changes"]
    expression = next(row for row in changes if row["path"].endswith("/expression"))
    assert (expression["before"], expression["after"]) == ("MIT", "GPL-3.0-only")
    assert expression["source_ids_before"] == [base.licenses[0].id]
    assert expression["source_ids_after"] == [target.licenses[0].id]
    assert all(row["source_ids_before"] or row["source_ids_after"] for row in changes)


def test_scan_local_license_ids_do_not_create_resource_or_license_changes(env):
    before_license = _license(101, "MIT", verification="verified")
    after_license = _license(201, "MIT", verification="verified")
    base = snapshot(env, 1, lambda payload: payload.update(
        licenses=[before_license],
        components=[_component_with_license(1, "1.0", before_license["id"], "alpha")],
    ))
    target = snapshot(env, 2, lambda payload: payload.update(
        licenses=[after_license],
        components=[_component_with_license(2, "1.0", after_license["id"], "alpha")],
    ))
    result = diff(env, base, target)
    assert result["resources"] == []
    assert result["license_observation_changes"] == []
    assert result["verification_changes"] == []


def test_all_five_change_categories_preserve_empty_string_distinct_from_null():
    value = copy.deepcopy(EXAMPLES["ScanDiffView"])
    scalar = {"path": "/field", "before": "", "after": None}
    fact = {
        "source_ids_before": ["source-before"],
        "source_ids_after": [],
        **scalar,
        "evidence_refs": [],
    }
    value["resources"][0]["field_changes"] = [copy.deepcopy(scalar)]
    value["license_observation_changes"] = [copy.deepcopy(fact)]
    value["verification_changes"] = [copy.deepcopy(fact)]
    value["finding_changes"] = [copy.deepcopy(fact)]
    value["assessment_diff"]["changes"] = [copy.deepcopy(fact)]

    validator("ScanDiffView").validate(value)
    groups = [
        value["resources"][0]["field_changes"],
        value["license_observation_changes"],
        value["verification_changes"],
        value["finding_changes"],
        value["assessment_diff"]["changes"],
    ]
    assert all(group[0]["before"] == "" and group[0]["after"] is None for group in groups)
    assert '"before": ""' in json.dumps(value) and '"after": null' in json.dumps(value)


def test_assessment_license_obligation_and_restriction_leaf_changes_without_ai(env):
    def with_component(payload):
        payload["components"] = [component()]

    base = snapshot(env, 1, with_component)
    target = snapshot(env, 2, lambda payload: payload.update(components=[component(2)]))
    assessment(env, base)

    def mutate(value):
        value.update(ai_status="succeeded", ai_summary="QWEN MUST NOT ENTER FORMAL DIFF")
        value["resource_evaluations"][0]["license_expression"] = "Apache-2.0"
        value["resource_evaluations"][0]["restrictions"] = {
            "closed_distribution": ["retain notices"]
        }
        if value["obligations"]:
            value["obligations"][0]["requirement"] = "retain changed notice"
        else:
            value["obligations"].append({
                "id": "assessment-obligation",
                "action": "retain_license_notice",
                "requirement": "retain changed notice",
                "trigger": "distribution",
                "fulfillment": "pending",
                "resource_ids": [value["resource_evaluations"][0]["resource_id"]],
                "evidence_ids": value["resource_evaluations"][0]["evidence_ids"],
                "rule_id": "license.notice.review",
                "rule_version": "1.0",
            })

    assessment(env, target, mutate=mutate)
    result = diff(env, base, target)["assessment_diff"]
    assert result["status"] == "compared"
    assert any(row["path"].endswith("/license_expression") and row["after"] == "Apache-2.0" for row in result["changes"])
    assert any("/restrictions/closed_distribution/" in row["path"] and row["after"] == "retain notices" for row in result["changes"])
    assert any(row["path"].endswith("/requirement") and row["after"] == "retain changed notice" for row in result["changes"])
    assert "QWEN" not in json.dumps(result)


def test_identity_is_case_safe_but_unknown_identity_is_never_guessed(env):
    base = snapshot(env, 1, comps(component(name="Requests", purl=False)))
    target = snapshot(env, 2, comps(component(2, name="requests", purl=False)))
    rows = diff(env, base, target)["resources"]
    assert len(rows) == 1 and rows[0]["kind"] == "changed"
    assert rows[0]["before"]["resource_identity_key"] == rows[0]["after"]["resource_identity_key"]
    assert any(change["path"].endswith("/name") and change["before"] == "Requests" and change["after"] == "requests"
               for change in rows[0]["field_changes"])

    unknown_base = snapshot(env, 3, comps(component(3, name="Same", ecosystem="unknown", purl=False)))
    unknown_target = snapshot(env, 4, comps(component(4, name="same", ecosystem="unknown", purl=False)))
    rows = diff(env, unknown_base, unknown_target)["resources"]
    assert len(rows) == 2
    assert {row["kind"] for row in rows} == {"unmatched"}
    assert all((row["before"] or row["after"])["resource_identity_key"] is None for row in rows)


def test_reliable_identity_distinguishes_ambiguous_from_unmatched(env):
    base = snapshot(env, 1, comps(component(1, "1"), component(2, "2")))
    target = snapshot(env, 2, comps(component(3, "3"), component(4, "4")))
    assert {row["kind"] for row in diff(env, base, target)["resources"]} == {"ambiguous"}

    unknown_base = snapshot(env, 3, comps(component(5, ecosystem="unknown", purl=False)))
    unknown_target = snapshot(env, 4, comps(component(6, ecosystem="unknown", purl=False)))
    assert {row["kind"] for row in diff(env, unknown_base, unknown_target)["resources"]} == {"unmatched"}


def test_reordering_is_stable_and_get_remains_read_only(env, monkeypatch):
    first = component(1, "1.0", name="alpha")
    second = component(2, "2.0", name="beta")
    base = snapshot(env, 1, comps(first, second))
    target = snapshot(env, 2, comps(copy.deepcopy(second), copy.deepcopy(first)))
    before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in env.path.iterdir() if path.is_file()}

    def forbidden(*args, **kwargs):
        raise AssertionError("Diff GET attempted a write")

    monkeypatch.setattr(env.registry, "create", forbidden)
    monkeypatch.setattr(env.registry, "replace", forbidden)
    monkeypatch.setattr(env.store, "create", forbidden)
    results = [diff(env, base, target) for _ in range(2)]
    for result in results:
        result["provenance"].pop("generated_at")
    after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in env.path.iterdir() if path.is_file()}

    assert results[0] == results[1]
    assert results[0]["resources"] == []
    assert before == after


@pytest.mark.parametrize("field", ["path", "source_id", "evidence_id"])
def test_empty_structural_identifiers_remain_rejected(field):
    value = copy.deepcopy(EXAMPLES["ScanDiffView"])
    value["license_observation_changes"] = [{
        "source_ids_before": ["source-before"],
        "source_ids_after": ["source-after"],
        "path": "/expression",
        "before": "",
        "after": None,
        "evidence_refs": [{"namespace": "scan", "scan_id": "scan", "evidence_id": "evidence"}],
    }]
    row = value["license_observation_changes"][0]
    if field == "path":
        row["path"] = ""
    elif field == "source_id":
        row["source_ids_before"] = [""]
    else:
        row["evidence_refs"][0]["evidence_id"] = ""
    assert list(validator("ScanDiffView").iter_errors(value))
