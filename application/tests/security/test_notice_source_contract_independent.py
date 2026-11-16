import pytest

from app.notice_source.models import (Binding, Content, Coverage, NoticeObservation,
                                      NoticeSourceCollection, Producer, Relation,
                                      bind_notice_source_collection, validate_notice_source_package)


def test_rejects_package_hash_tampering_independently():
    collection = NoticeSourceCollection(
        schema_version="openguard.notice-source/1", observed_at="2026-09-24T00:00:00Z",
        coverage=Coverage(state="completed"), observations=[NoticeObservation(
            observation_key="n", locator="NOTICE", content=Content(state="not_observed"),
            collector=Producer(type="collector", name="test", version="1"),
            relation=Relation(state="unresolved", basis="no_unique_resource_binding"),
        )],
    )
    value = bind_notice_source_collection(collection, binding=Binding(
        scan_id="s", registry_revision="r", input_digest="1" * 64,
        inventory_digest="2" * 64, facts_hash="3" * 64,
    )).model_dump(mode="json")
    value["package_hash"] = "0" * 64
    with pytest.raises(Exception):
        validate_notice_source_package(value)


@pytest.mark.parametrize(
    ("state", "gaps"),
    [
        ("not_observed", []),
        ("not_scanned", ["read_budget_exhausted"]),
        ("read_failed", ["read_failed"]),
    ],
)
def test_non_retained_states_reject_text_and_keep_explicit_reason(state, gaps):
    assert Content(state=state, gap_codes=gaps).text is None
    with pytest.raises(Exception):
        Content(state=state, text="invented", gap_codes=gaps)


def test_retained_content_rejects_hash_and_range_mismatch():
    with pytest.raises(Exception):
        Content(state="full", text="NOTICE", encoding="utf-8", byte_range=[0, 6], truncated=False,
                retained_bytes_sha256="0" * 64, whole_bytes_sha256="0" * 64)


def test_relation_ambiguity_cannot_claim_subject():
    with pytest.raises(Exception):
        Relation(state="unresolved", subject="resource:guessed", basis="ambiguous")
    assert Relation(state="unresolved", subject=None, basis="ambiguous").basis == "ambiguous"
