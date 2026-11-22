"""One exposed real repository snapshot and adversarial mutations."""

from dataclasses import replace
import hashlib
from pathlib import Path
import subprocess

import pytest

from app.p2.contract import Subject
from app.p2b._apache_redistribution import EvidenceRef, ReviewedBinding, ReviewedUseFact, assess_redistribution
from app.p2b.materials import MAX_MATERIAL_BYTES
from app.rules.engine import load_ruleset


ROOT = Path(__file__).resolve().parents[2]
REVISION = "2cc7f63a812561bf71de11d2041e4027a345efda"
SCOPE = "first_party_code_and_docs"
SUBJECT = Subject(resource_id="openguard:first-party", version=REVISION)
LICENSE = EvidenceRef(
    "test:openguard:license", "LICENSE",
    "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
)
README = EvidenceRef(
    "test:openguard:scope", "README.md",
    "2941166b3c8574882c34d4af2a6d8af7a5b827b7701e4978813305808b71f4ea",
)
BINDING = ReviewedBinding(SUBJECT.resource_id, REVISION, SCOPE, LICENSE, README)


@pytest.fixture
def check():
    inputs = {
        "subject": SUBJECT,
        "scope": SCOPE,
        "distribution": "planned",
        "binding": BINDING,
        "evidence_bytes": {
            reference.evidence_id: subprocess.check_output(
                ["git", "show", f"{REVISION}:{reference.path}"], cwd=ROOT,
            )
            for reference in (LICENSE, README)
        },
        "declared_license": "Apache-2.0",
        "ruleset": load_ruleset(),
    }

    def run(**overrides):
        return assess_redistribution(**(inputs | overrides))

    return run, inputs


def test_real_repo_license_gives_locatable_conditional_claim(check):
    run, inputs = check
    assessment = run()
    assert assessment == run()
    assert assessment.status == "conditional"
    assert assessment.subject == SUBJECT
    assert assessment.use == "distributed"
    assert assessment.gap is None
    link = assessment.link
    assert link.claim == "provide_license_copy_to_recipients_if_redistributed"
    assert link.clause == "Apache-2.0 §4(a)"
    assert link.rule_id == "LIC-APACHE-2.0-NOTICE"
    assert link.ruleset_sha256 == inputs["ruleset"].source_digest
    assert "obligation_fulfillment" in link.unresolved
    for location, excerpt in (
        (link.license_evidence, b"Derivative Works a copy of this License"),
        (link.scope_evidence, "第三方软件".encode("utf-8")),
    ):
        source = inputs["evidence_bytes"][location.reference.evidence_id]
        assert excerpt in source[location.start_byte:location.end_byte_exclusive]
        assert location.start_line == source[:location.start_byte].count(b"\n") + 1
        assert location.end_line == source[:location.end_byte_exclusive].count(b"\n") + 1


@pytest.mark.parametrize(("overrides", "category", "reason"), [
    ({"subject": Subject(resource_id=SUBJECT.resource_id, version="0" * 40)},
     "evidence_conflict", "subject_binding_mismatch"),
    ({"subject": Subject(resource_id="npm:express", version=REVISION)},
     "evidence_conflict", "subject_binding_mismatch"),
    ({"scope": "all_project_dependencies"}, "evidence_conflict", "subject_binding_mismatch"),
    ({"scope": None}, "user_fact_missing", "subject_version_or_scope_unknown"),
    ({"subject": Subject(resource_id=SUBJECT.resource_id, version=None)},
     "user_fact_missing", "subject_version_or_scope_unknown"),
    ({"distribution": "unknown"}, "user_fact_missing", "distribution_unknown"),
    ({"distribution": "user_says_excluded"}, "user_fact_missing", "distribution_unknown"),
    ({"binding": None}, "missing_material", "reviewed_binding_missing"),
    ({"evidence_bytes": {}}, "missing_material", "evidence_reference_unresolved"),
    ({"binding": replace(BINDING, scope_statement=LICENSE)}, "evidence_conflict", "invalid_evidence_references"),
    ({"declared_license": "MIT"}, "evidence_conflict", "license_text_declaration_mismatch"),
    ({"declared_license": "Apache-2.0 OR MIT"}, "unsupported", "license_expression_unsupported"),
    ({"declared_license": "Apache-2.0 AND MIT"}, "unsupported", "license_expression_unsupported"),
    ({"declared_license": "Apache-2.0 WITH LLVM-exception"}, "unsupported", "license_expression_unsupported"),
])
def test_refusals_do_not_create_links(check, overrides, category, reason):
    run, _ = check
    assessment = run(**overrides)
    assert assessment.status == "review_required"
    assert assessment.link is None
    assert (assessment.gap.category, assessment.gap.reason) == (category, reason)
    assert assessment.gap.next_action


@pytest.mark.parametrize(("raw", "repin", "category", "reason"), [
    (b"", False, "missing_material", "empty_material"),
    (b" ", True, "parse_failure", "material_empty_text"),
    (b"\xff", True, "parse_failure", "material_utf8_required"),
    (b"\x00", True, "parse_failure", "material_binary_content"),
    (b"x" * (MAX_MATERIAL_BYTES + 1), False, "unsupported", "material_size_or_type_unsupported"),
    (b"Apache License\nVersion 2.0", False, "evidence_conflict", "evidence_hash_mismatch"),
    (b"Apache License\nVersion 2.0\nAdditional restrictions apply.", True, "unsupported", "license_text_not_reviewed"),
], ids=[
    "zero-bytes", "blank-text", "invalid-utf8", "binary", "oversize",
    "wrong-hash", "additional-terms",
])
def test_distinguishes_material_failures(check, raw, repin, category, reason):
    run, inputs = check
    binding = BINDING
    if repin:
        binding = replace(BINDING, license_text=replace(LICENSE, sha256=hashlib.sha256(raw).hexdigest()))
    assessment = run(binding=binding, evidence_bytes=inputs["evidence_bytes"] | {LICENSE.evidence_id: raw})
    assert assessment.status == "review_required"
    assert assessment.link is None
    assert (assessment.gap.category, assessment.gap.reason) == (category, reason)


def test_valid_hash_without_scope_statement_cannot_support_claim(check):
    run, inputs = check
    raw = b"Unrelated material"
    binding = replace(BINDING, scope_statement=replace(README, sha256=hashlib.sha256(raw).hexdigest()))
    assessment = run(binding=binding, evidence_bytes=inputs["evidence_bytes"] | {README.evidence_id: raw})
    assert assessment.link is None
    assert assessment.gap.reason == "scope_statement_unresolved"


def test_unknown_rule_version_requires_review(check):
    run, inputs = check
    ruleset = inputs["ruleset"]
    rules = tuple(replace(rule, version="2.0.0") for rule in ruleset.rules)
    assessment = run(ruleset=replace(ruleset, rules=rules))
    assert assessment.link is None
    assert assessment.gap.reason == "rule_version_unsupported"


def test_non_applicability_requires_positive_basis_and_resolved_evidence(check):
    run, inputs = check
    assert run(distribution="verified_absent").gap.reason == "no_distribution_evidence_missing"
    raw = b"Synthetic reviewed delivery inventory: bound resource absent."
    reference = EvidenceRef("test:delivery-review", "delivery-inventory.txt", hashlib.sha256(raw).hexdigest())
    reviewed = ReviewedUseFact(SUBJECT.resource_id, REVISION, SCOPE, reference)
    binding = replace(BINDING, no_distribution_evidence=reviewed)
    result = run(
        distribution="verified_absent", binding=binding,
        evidence_bytes=inputs["evidence_bytes"] | {reference.evidence_id: raw},
    )
    assert result.status == "not_applicable"
    assert result.link is None
    assert result.gap.reason == "verified_no_redistribution"
    assert result.applicability_evidence == reference
    refused = run(distribution="verified_absent", binding=binding)
    assert refused.status == "review_required"
    assert refused.gap.category == "missing_material"
    wrong_scope = replace(binding, no_distribution_evidence=replace(reviewed, scope="all_dependencies"))
    assert run(
        distribution="verified_absent", binding=wrong_scope,
        evidence_bytes=inputs["evidence_bytes"] | {reference.evidence_id: raw},
    ).gap.reason == "use_fact_binding_mismatch"


def test_real_license_modified_files_clause_with_reviewed_synthetic_delivery_fact(check):
    run, inputs = check
    raw = b"Synthetic planned delivery: modified first-party files in the reviewed scope."
    fact = EvidenceRef("test:modified-delivery", "delivery-plan.txt", hashlib.sha256(raw).hexdigest())
    reviewed = ReviewedUseFact(SUBJECT.resource_id, REVISION, SCOPE, fact)
    binding = replace(BINDING, modified_files_evidence=reviewed)
    evidence = inputs["evidence_bytes"] | {fact.evidence_id: raw}
    result = run(clause="4(b)", binding=binding, evidence_bytes=evidence)
    assert result.status == "conditional"
    assert result.distribution == "planned"
    assert result.link.clause == "Apache-2.0 §4(b)"
    assert result.link.claim == "mark_modified_files_if_redistributed"
    assert result.link.use_evidence == fact
    assert result.link.rule_version == "1.0.0"
    location = result.link.license_evidence
    assert (location.start_line, location.end_line) == (97, 98)
    assert b"stating that You changed the files" in evidence[LICENSE.evidence_id][
        location.start_byte:location.end_byte_exclusive
    ]
    for mutation, reason in (
        ({"binding": BINDING}, "modified_delivery_scope_unknown"),
        ({"binding": binding}, "evidence_reference_unresolved"),
        ({"binding": binding, "evidence_bytes": evidence | {fact.evidence_id: b"Alleged plan"}}, "evidence_hash_mismatch"),
        ({"binding": replace(BINDING, modified_files_evidence=replace(reviewed, reference=README))}, "invalid_evidence_references"),
        ({"binding": replace(BINDING, modified_files_evidence=replace(reviewed, resource_id="npm:express"))}, "use_fact_binding_mismatch"),
        ({"binding": replace(BINDING, modified_files_evidence=replace(reviewed, revision="0" * 40))}, "use_fact_binding_mismatch"),
        ({"binding": replace(BINDING, modified_files_evidence=replace(reviewed, scope="all_dependencies"))}, "use_fact_binding_mismatch"),
        ({"binding": binding, "distribution": "unknown"}, "distribution_unknown"),
    ):
        decision = run(clause="4(b)", **mutation)
        assert decision.link is None
        assert decision.gap.reason == reason


def test_bound_planned_use_fact_is_resolved_and_retained(check):
    run, inputs = check
    raw = b"Synthetic reviewed release plan for the pinned first-party scope."
    fact = EvidenceRef("test:planned-delivery", "release-plan.txt", hashlib.sha256(raw).hexdigest())
    binding = replace(BINDING, planned_distribution_evidence=ReviewedUseFact(SUBJECT.resource_id, REVISION, SCOPE, fact))
    assert run(binding=binding).gap.reason == "evidence_reference_unresolved"
    result = run(binding=binding, evidence_bytes=inputs["evidence_bytes"] | {fact.evidence_id: raw})
    assert result.distribution == "planned"
    assert result.link.planned_distribution_evidence == fact
