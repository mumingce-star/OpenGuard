"""Independent B02 detector probes: only already-loaded facts may be consumed."""

from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess

import pytest

from app.detectors.license_notice_facts import canonical_facts_sha256, detect_license_notice_candidates


def _facts() -> dict:
    return json.loads(
        (Path("tests/fixtures/notice-license-facts-v2/facts.json")).read_text(encoding="utf-8")
    )


def _detect(value: dict):
    return detect_license_notice_candidates(
        value,
        expected_package_sha256=canonical_facts_sha256(value),
    )


def test_detector_is_offline_and_never_changes_pending_to_verified(monkeypatch: pytest.MonkeyPatch) -> None:
    value = _facts()

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected external capability")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    first = _detect(value)
    second = _detect(value)

    assert first == second
    assert first.obligations == ()
    assert all(candidate.authorization_status == "pending" for candidate in first.findings)
    assert all(candidate.license_expression_id is None for candidate in first.findings)
    assert all(candidate.status == "review_required" for candidate in first.findings)


def test_detector_does_not_treat_notice_absence_as_a_violation() -> None:
    candidates = _detect(_facts())
    root_notice = next(item for item in candidates.findings if item.code == "GAP_ROOT_NOTICE_MISSING")

    assert root_notice.category == "evidence_gap"
    assert root_notice.status == "review_required"
    assert root_notice.fact_id == "fact.root.openguard"
    assert root_notice.confirmed_violation is False
