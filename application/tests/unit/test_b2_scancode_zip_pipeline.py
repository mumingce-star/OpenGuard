from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.scanners.external_tools import parse_json_output, run_json_tool, run_scancode_license_scan


def test_scancode_command_is_fixed_to_license_json_and_rejects_host_path() -> None:
    with pytest.raises(ValueError, match="trusted proc descriptor"):
        run_scancode_license_scan("scancode", "relative/tree", pass_fds=())


def test_real_scancode_license_output_maps_to_pending_evidence() -> None:
    """Opt-in integration regression; a CI runner supplies the fixed executable."""
    import os
    from pathlib import Path
    from app.scanners.external_tools import map_scancode_output

    executable = os.environ.get("OPENGUARD_SCANCODE_BIN")
    if not executable or os.name != "posix":
        pytest.skip("a Linux runner with OPENGUARD_SCANCODE_BIN is required")
    fixture = Path(__file__).parents[1] / "fixtures" / "scancode-real"
    execution = run_json_tool(executable, ("--license", "--json", "-", str(fixture)))
    payload = parse_json_output(execution)
    assert payload is not None
    mapped = map_scancode_output(payload, root_digest="0" * 64, observed_at=datetime(2026, 9, 3, tzinfo=timezone.utc), tool_version="32.5.0")
    assert "mit" in mapped.license_candidates
    assert any(item.locator == "LICENSE" for item in mapped.evidence)
