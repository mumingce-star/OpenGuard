"""Opt-in regression against a real Syft JSON document.

The executable is supplied by the controlled runner rather than committed to
the repository.  The fixture contains only a tiny public npm lockfile.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.scanners.external_tools import map_syft_output, parse_json_output, run_json_tool
from app.scanners.syft_pipeline import _relative_locations


def test_real_syft_json_maps_a_locatable_npm_component() -> None:
    executable = os.environ.get("OPENGUARD_SYFT_BIN")
    if not executable:
        pytest.skip("set OPENGUARD_SYFT_BIN to a controlled Syft executable")

    fixture = Path(__file__).parents[1] / "fixtures" / "syft-real"
    execution = run_json_tool(
        executable,
        ("scan", f"dir:{fixture}", "-o", "syft-json"),
        disable_update_check=True,
    )
    payload = parse_json_output(execution)
    assert payload is not None

    mapped = map_syft_output(
        _relative_locations(payload, str(fixture)),
        root_digest="0" * 64,
        observed_at=datetime(2026, 9, 4, tzinfo=timezone.utc),
        tool_version="1.51.0",
    )

    component = next(item for item in mapped.components if item.purl == "pkg:npm/is-number@7.0.0")
    assert component.ecosystem == "npm"
    assert component.license_expression_id is None
    assert [item.locator for item in mapped.evidence] == ["package-lock.json", "package-lock.json"]
