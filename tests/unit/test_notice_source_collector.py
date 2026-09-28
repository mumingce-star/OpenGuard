import hashlib
from datetime import datetime, timezone

from app.ingestion.inventory import Inventory, InventoryEntry
from app.notice_source import (NoticeSourceCandidate, bind_notice_source_collection,
                               collect_notice_source_package, validate_notice_source_package)
from app.notice_source.models import Binding, Producer


class Session:
    def __init__(self, files):
        self.files = files
        self.inventory = Inventory(tuple(InventoryEntry(path, len(data), hashlib.sha256(data).hexdigest())
                                         for path, data in files.items()), "a" * 64)
        self.remaining_read_bytes = 16 * 1024 * 1024

    def read_bytes(self, path, *, max_bytes):
        data = self.files[path]
        if len(data) > max_bytes:
            raise AssertionError("collector widened read limit")
        self.remaining_read_bytes -= len(data)
        return data


def binding():
    return Binding(scan_id="scan-demo", registry_revision="r1", input_digest="1" * 64,
                   inventory_digest="2" * 64, facts_hash="3" * 64)


def producer():
    return Producer(type="collector", name="openguard.notice-source", version="1", config_digest="4" * 64)


def test_collects_full_and_utf8_boundary_excerpt_without_formal_resource_ids():
    full = b"NOTICE\nexample\n"
    long = ("你" * 30_000).encode("utf-8")
    package = collect_notice_source_package(
        Session({"NOTICE": full, "third_party/NOTICE": long}),
        observed_at=datetime(2026, 9, 24, tzinfo=timezone.utc), collector=producer(),
        candidates=(NoticeSourceCandidate("root-notice", "NOTICE"),
                    NoticeSourceCandidate("dependency-notice", "third_party/NOTICE", "resolved", "dependency:demo", "unique_manifest_evidence")),
    )
    assert package.coverage.state == "completed"
    assert package.observations[0].content.state == "full"
    assert package.observations[1].content.state == "excerpt"
    assert package.observations[1].content.byte_range[1] <= 4 * 1024
    assert package.observations[1].relation.subject == "dependency:demo"
    terminal = bind_notice_source_collection(package, binding=binding())
    assert validate_notice_source_package(terminal.model_dump(mode="json")).package_hash == terminal.package_hash


def test_reports_unreadable_inputs_as_gaps_and_does_not_claim_observed_bytes():
    package = collect_notice_source_package(
        Session({"NOTICE": b"\xff"}), observed_at=datetime.now(timezone.utc), collector=producer(),
        candidates=(NoticeSourceCandidate("invalid", "NOTICE"), NoticeSourceCandidate("missing", "MISSING")),
    )
    assert package.coverage.state == "partial"
    assert [item.content.state for item in package.observations] == ["not_scanned", "not_scanned"]
    assert package.observations[0].content.whole_bytes_sha256 is None
    assert set(package.coverage.gap_codes) == {"utf8_decode_failed", "path_not_in_inventory"}


def test_preserves_session_budget_and_reports_io_failure_without_retrying():
    exhausted = Session({"NOTICE": b"NOTICE"})
    exhausted.remaining_read_bytes = 0
    budget_package = collect_notice_source_package(
        exhausted, observed_at=datetime.now(timezone.utc), collector=producer(),
        candidates=(NoticeSourceCandidate("budget", "NOTICE"),),
    )
    assert budget_package.coverage.state == "partial"
    assert budget_package.observations[0].content.gap_codes == ["read_budget_exhausted"]
    assert "binding" not in budget_package.model_dump(mode="json")

    class BrokenSession(Session):
        def read_bytes(self, path, *, max_bytes):
            raise ValueError("simulated_read_failure")

    failed = collect_notice_source_package(
        BrokenSession({"NOTICE": b"NOTICE", "SECOND": b"NOTICE"}), observed_at=datetime.now(timezone.utc),
        collector=producer(), candidates=(NoticeSourceCandidate("first", "NOTICE"), NoticeSourceCandidate("second", "SECOND")),
    )
    assert [item.content.state for item in failed.observations] == ["read_failed", "not_scanned"]
    assert set(failed.coverage.gap_codes) == {"read_failed", "prior_read_failed"}
