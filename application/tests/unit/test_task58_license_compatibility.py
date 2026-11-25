"""TASK58: deterministic project-level license compatibility matrix, CLI v2, and ASGI API."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile

import pytest

from app.licenses.compatibility import (
    PROPRIETARY,
    RULE_VERSION,
    SCHEMA_VERSION,
    SUPPORTED_SPDX,
    SUPPORTED_TARGETS,
    canonicalize_compatibility_expression,
    evaluate_pairwise_atomic,
    evaluate_pairwise_expressions,
    evaluate_scan_compatibility,
    evaluate_target_expression,
    evaluate_target_pair,
    normalize_target_license,
)
from test_task45_dependency_evidence_real_zip import ORIGIN, _checked, _open_zip_gateway


ROOT = Path(__file__).resolve().parents[3]
SAMPLE = "samples/is-number-7.0.0-derived.zip"


def test_supported_targets_and_normalization():
    assert SUPPORTED_TARGETS == (PROPRIETARY, *SUPPORTED_SPDX)
    assert len(SUPPORTED_SPDX) == 22
    assert normalize_target_license(None) is None
    assert normalize_target_license("   ") is None
    assert normalize_target_license("proprietary") == PROPRIETARY
    assert normalize_target_license("mit") == "MIT"
    assert normalize_target_license("Apache 2.0") == "Apache-2.0"
    assert normalize_target_license("gpl 2.0 or later") == "GPL-2.0-or-later"
    for bad in ("MIT OR Apache-2.0", "MIT AND ISC", "WTFPL", "Unknown-1.0"):
        with pytest.raises(ValueError, match="invalid_target_license"):
            normalize_target_license(bad)


@pytest.mark.parametrize(("target", "dep", "usage", "expected_status", "expected_rule"), [
    ("MIT", "MIT", {"distributed": True}, "COMPATIBLE", "COMPAT-PERMISSIVE-INBOUND"),
    ("PROPRIETARY", "BSD-3-Clause", {"commercial": True, "distributed": True}, "COMPATIBLE", "COMPAT-PERMISSIVE-INBOUND"),
    ("PROPRIETARY", "Apache-2.0", {"commercial": True, "distributed": True}, "COMPATIBLE", "COMPAT-APACHE2-INBOUND"),
    ("GPL-2.0-only", "Apache-2.0", {"distributed": True}, "INCOMPATIBLE", "COMPAT-APACHE2-GPL2-ONLY"),
    ("GPL-2.0-only", "Apache-2.0", {"distributed": False}, "REVIEW_REQUIRED", "COMPAT-APACHE2-GPL2-ONLY"),
    ("GPL-2.0-or-later", "Apache-2.0", {"distributed": True}, "CONDITIONAL", "COMPAT-APACHE2-INTO-GPL3-FAMILY"),
    ("GPL-3.0-only", "Apache-2.0", {"distributed": True}, "CONDITIONAL", "COMPAT-APACHE2-INTO-GPL3-FAMILY"),
    ("GPL-3.0-only", "GPL-2.0-only", {"distributed": True}, "INCOMPATIBLE", "COMPAT-GPL-VERSION-CONFLICT"),
    ("GPL-3.0-only", "GPL-2.0-or-later", {"distributed": True}, "CONDITIONAL", "COMPAT-GPL-VERSION-CONVERSION"),
    ("MIT", "GPL-3.0-only", {"distributed": True}, "INCOMPATIBLE", "COMPAT-STRONG-COPYLEFT-PROPAGATION"),
    ("MIT", "GPL-3.0-only", {"distributed": False}, "REVIEW_REQUIRED", "COMPAT-STRONG-COPYLEFT-PROPAGATION"),
    ("PROPRIETARY", "AGPL-3.0-only", {"distributed": False, "network_service": True}, "INCOMPATIBLE", "COMPAT-AGPL-NETWORK-COPYLEFT"),
    ("PROPRIETARY", "AGPL-3.0-only", {"distributed": False, "network_service": False}, "REVIEW_REQUIRED", "COMPAT-AGPL-NETWORK-COPYLEFT"),
    ("GPL-3.0-only", "CDDL-1.0", {"distributed": True}, "INCOMPATIBLE", "COMPAT-RECIPROCAL-VS-GPL"),
    ("GPL-3.0-only", "EPL-2.0", {"distributed": True}, "INCOMPATIBLE", "COMPAT-RECIPROCAL-VS-GPL"),
    ("GPL-3.0-only", "MPL-2.0", {"distributed": True}, "CONDITIONAL", "COMPAT-MPL2-SECONDARY"),
    ("PROPRIETARY", "MPL-2.0", {"distributed": True}, "REVIEW_REQUIRED", "COMPAT-MPL2-FILE-COPYLEFT"),
    ("GPL-2.0-only", "LGPL-3.0-only", {"distributed": True}, "INCOMPATIBLE", "COMPAT-LGPL3-GPL2-ONLY"),
    ("PROPRIETARY", "LGPL-2.1-only", {"distributed": True}, "REVIEW_REQUIRED", "COMPAT-LGPL-LINKING"),
    ("MIT", "CC-BY-NC-4.0", {"commercial": True, "distributed": False}, "INCOMPATIBLE", "COMPAT-CC-BY-NC-COMMERCIAL"),
    ("MIT", "CC-BY-NC-4.0", {"commercial": False, "distributed": True}, "INCOMPATIBLE", "COMPAT-CC-BY-NC-OSI-OUTBOUND"),
    ("PROPRIETARY", "CC-BY-NC-4.0", {"commercial": False, "distributed": False}, "REVIEW_REQUIRED", "COMPAT-CC-BY-NC-SCOPE"),
    ("GPL-2.0-only", "CC-BY-4.0", {"distributed": True}, "INCOMPATIBLE", "COMPAT-CC-BY-4-GPL2"),
])
def test_atomic_target_rules(target, dep, usage, expected_status, expected_rule):
    verdict = evaluate_target_pair(target, dep, usage)
    assert verdict["status"] == expected_status
    assert verdict["rule_id"] == expected_rule


def test_compound_or_and_unknown_target_expressions():
    dual = evaluate_target_expression("PROPRIETARY", "MIT OR GPL-2.0-only", {"distributed": True})
    assert dual["status"] == "CONDITIONAL"
    assert dual["rule_id"] == "COMPAT-OR-BRANCH-SELECTED"
    assert dual["chosen_branch"] == "MIT"

    conjunction = evaluate_target_expression("PROPRIETARY", "MIT AND GPL-2.0-only", {"distributed": True})
    assert conjunction["status"] == "INCOMPATIBLE"

    mixed = evaluate_target_expression("MIT", "MIT AND Apache-2.0 OR ISC", {"distributed": True})
    assert mixed["status"] == "UNKNOWN"
    assert mixed["rule_id"] == "COMPAT-COMPLEX-EXPRESSION"

    unrecognized = evaluate_target_expression("MIT", "WTFPL", {"distributed": True})
    assert unrecognized["status"] == "UNKNOWN"

    no_target = evaluate_target_expression(None, "MIT", {"distributed": True})
    assert no_target["status"] == "UNKNOWN" and no_target["rule_id"] == "COMPAT-TARGET-UNRESOLVED"


def test_pairwise_rules_and_symmetry():
    for left, right, expected_status, expected_rule in (
        ("GPL-2.0-only", "Apache-2.0", "INCOMPATIBLE", "PAIR-GPL2-ONLY-APACHE2"),
        ("GPL-2.0-only", "GPL-3.0-only", "INCOMPATIBLE", "PAIR-GPL2-ONLY-GPL3-FAMILY"),
        ("GPL-3.0-only", "CDDL-1.0", "INCOMPATIBLE", "PAIR-GPL-RECIPROCAL"),
        ("MIT", "CC-BY-NC-4.0", "INCOMPATIBLE", "PAIR-OSI-NONCOMMERCIAL"),
        ("GPL-2.0-or-later", "Apache-2.0", "CONDITIONAL", "PAIR-APACHE2-GPL3-COMBINATION"),
    ):
        a = evaluate_pairwise_atomic(left, right, {"distributed": True, "commercial": False})
        b = evaluate_pairwise_atomic(right, left, {"distributed": True, "commercial": False})
        assert a["status"] == b["status"] == expected_status
        assert a["rule_id"] == b["rule_id"] == expected_rule

    dual_pair = evaluate_pairwise_expressions("MIT OR GPL-2.0-only", "Apache-2.0", {"distributed": True})
    assert dual_pair["status"] == "CONDITIONAL"
    assert dual_pair["rule_id"] == "PAIR-OR-BRANCH-SELECTION"


def _package_copy(tmp_path):
    copy = tmp_path / "pkg"
    for relative in (
        "deployment", "application/backend/app", "application/examples",
        "application/rules", "application/schemas", "samples",
    ):
        shutil.copytree(ROOT / relative, copy / relative, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(ROOT / "openguard.py", copy / "openguard.py")
    return copy


def _run_cli(package, scratch, *arguments):
    isolated_tmp = scratch / "cmd-tmp"
    isolated_tmp.mkdir(exist_ok=True)
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("OPENGUARD_")
        and key not in {"_OPENGUARD_SCAN_REEXEC", "PYTHONHOME", "PYTHONPATH", "PYTHONDONTWRITEBYTECODE"}
    }
    env.update(TMPDIR=str(isolated_tmp), TMP=str(isolated_tmp), TEMP=str(isolated_tmp), PYTHONNOUSERSITE="1")
    return subprocess.run(
        [sys.executable, "-B", str(package / "openguard.py"), "scan", *map(str, arguments)],
        cwd=package, env=env, capture_output=True, text=True, timeout=80,
    )


def _write_spdx_archive(path, root_license, dep_licenses):
    with ZipFile(path, "w") as zf:
        deps = {f"dep-{i}": "1.0.0" for i in range(len(dep_licenses))}
        pkg = {"name": "compat-root", "version": "1.0.0", "dependencies": deps}
        if root_license is not None:
            pkg["license"] = root_license
        zf.writestr("package.json", json.dumps(pkg))
        packages = {"": {"name": "compat-root", "version": "1.0.0", **({"license": root_license} if root_license is not None else {}), "dependencies": deps}}
        for i, lic in enumerate(dep_licenses):
            packages[f"node_modules/dep-{i}"] = {"version": "1.0.0", "license": lic}
        zf.writestr("package-lock.json", json.dumps({
            "name": "compat-root",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "packages": packages,
        }))


def test_headless_cli_v2_target_override_pairwise_conflict_and_fail_on(tmp_path):
    package = _package_copy(tmp_path)
    archive = tmp_path / "pair-conflict.zip"
    # No root license declared; two dependencies declare GPL-2.0-only and Apache-2.0.
    _write_spdx_archive(archive, None, ["GPL-2.0-only", "Apache-2.0"])

    # Without distributed, incompatible is 0 (REVIEW_REQUIRED), so --fail-on incompatible exits 0.
    internal = _run_cli(package, tmp_path, archive, "--format", "json", "--fail-on", "incompatible")
    assert internal.returncode == 0, internal.stderr
    doc_internal = json.loads(internal.stdout)
    assert doc_internal["schema_version"] == "openguard-cli-scan/2"
    compat_int = doc_internal["license_compatibility"]
    assert compat_int["schema_version"] == SCHEMA_VERSION
    assert compat_int["rule_version"] == RULE_VERSION
    assert compat_int["target"]["license"] is None
    assert compat_int["target"]["source"] == "undeclared"
    assert doc_internal["scan"]["incompatible_count"] == 0
    assert doc_internal["scan"]["review_required_count"] >= 1
    assert compat_int["pairwise_conflicts"][0]["status"] == "REVIEW_REQUIRED"

    # With distributed + --fail-on incompatible: pairwise GPL-2.0-only <-> Apache-2.0 triggers exit 1!
    dist = _run_cli(package, tmp_path, archive, "--format", "json", "--usage", "distributed", "--fail-on", "incompatible")
    assert dist.returncode == 1, dist.stderr
    doc_dist = json.loads(dist.stdout)
    assert doc_dist["scan"]["incompatible_count"] >= 1
    assert doc_dist["policy"]["triggered"] == ["incompatible"]
    assert doc_dist["license_compatibility"]["pairwise_conflicts"][0]["status"] == "INCOMPATIBLE"

    # Explicit --target-license PROPRIETARY under distributed triggers target INCOMPATIBLE on GPL-2.0-only.
    prop = _run_cli(package, tmp_path, archive, "--format", "markdown", "--target-license", "PROPRIETARY", "--usage", "distributed", "--fail-on", "incompatible")
    assert prop.returncode == 1
    assert "PROPRIETARY" in prop.stdout and "INCOMPATIBLE" in prop.stdout

    # Invalid --target-license fails closed with exit 2 and does not create output file.
    out_file = tmp_path / "should-not-exist.json"
    bad = _run_cli(package, tmp_path, package / SAMPLE, "--target-license", "NOT-VALID-SPDX", "--output", out_file)
    assert bad.returncode == 2 and "invalid_target_license" in bad.stderr and not out_file.exists()


def test_headless_cli_root_conflict_forces_target_unknown(tmp_path):
    package = _package_copy(tmp_path)
    profile = json.loads(
        (ROOT / "application/tests/fixtures/task49-copyleft-licenses.json").read_text(encoding="utf-8"),
    )["licenses"]["GPL-3.0"]
    tree = tmp_path / "conflict-root"
    tree.mkdir()
    (tree / "package.json").write_text(json.dumps({"name": "root-pkg", "version": "1.0.0", "license": "MIT", "dependencies": {"x": "1.0.0"}}), encoding="utf-8")
    raw = profile["text"].encode("utf-8")
    assert sha256(raw).hexdigest() == profile["sha256"]
    (tree / "LICENSE").write_bytes(raw)
    res = _run_cli(package, tmp_path, tree, "--format", "json")
    assert res.returncode == 0, res.stderr
    compat = json.loads(res.stdout)["license_compatibility"]
    assert compat["target"]["license"] is None
    assert compat["target"]["source"] == "root_conflict"
    assert compat["target"]["gaps"] == ["root_spdx_text_conflict"]


def test_asgi_license_compatibility_endpoint_contracts(tmp_path, monkeypatch):
    for gateway in _open_zip_gateway(tmp_path, monkeypatch):
        session = gateway.register("task58-compat-user")
        zip_path = tmp_path / "asgi-compat.zip"
        _write_spdx_archive(zip_path, "MIT", ["GPL-2.0-only", "Apache-2.0"])
        members = {}
        with ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                members[name] = zf.read(name)
        status_url, stored = gateway.upload(session, members, filename="task58-compat.zip")
        scan_path = status_url.removesuffix("/status")

        # Require auth.
        gateway.logout(session)
        _checked(gateway.client.get(scan_path + "/license-compatibility"), 401)
        session = gateway.register("task58-compat-user-2")
        status_url, stored = gateway.upload(session, members, filename="task58-compat-2.zip")
        scan_path = status_url.removesuffix("/status")

        # Bad query params and invalid target fail closed with 400.
        _checked(gateway.client.get(scan_path + "/license-compatibility", params={"unknown": "1"}), 400)
        _checked(gateway.client.get(scan_path + "/license-compatibility", params={"target_license": "MIT OR ISC"}), 400)

        # Auto-inferred MIT root (usage default distributed=False -> conservative REVIEW_REQUIRED).
        auto_resp = _checked(gateway.client.get(scan_path + "/license-compatibility"), 200)
        assert auto_resp.headers.get("cache-control") == "no-store"
        auto_data = auto_resp.json()
        assert auto_data["schema_version"] == SCHEMA_VERSION
        assert auto_data["target"]["license"] == "MIT"
        assert auto_data["target"]["source"] == "root_package"
        assert auto_data["formal_effect"] == "none"
        assert auto_data["model_calls"] == 0
        assert auto_data["summary"]["dependency_count"] == 2
        assert len(auto_data["pairwise_conflicts"]) >= 1
        assert auto_data["matrix"]["licenses"] == ["Apache-2.0", "GPL-2.0-only"]

        # Explicit target override to PROPRIETARY still returns RESOLVED PROPRIETARY.
        prop_resp = _checked(
            gateway.client.get(scan_path + "/license-compatibility", params={"target_license": "proprietary"}),
            200,
        ).json()
        assert prop_resp["target"]["license"] == "PROPRIETARY"
        assert prop_resp["target"]["source"] == "explicit"
        assert prop_resp["scan_ref"]["scan_id"] == stored.run.id


def test_headless_cli_network_service_usage_flag(tmp_path):
    """Audit Finding #1: --usage network_service is accepted and enforced."""
    package = _package_copy(tmp_path)
    archive = tmp_path / "agpl-network.zip"
    _write_spdx_archive(archive, "PROPRIETARY", ["AGPL-3.0-only"])

    res = _run_cli(
        package, tmp_path, archive,
        "--format", "json",
        "--target-license", "PROPRIETARY",
        "--usage", "network_service",
        "--fail-on", "incompatible",
    )
    assert res.returncode == 1, res.stderr
    doc = json.loads(res.stdout)
    assert doc["scan"]["usage"] == {
        "commercial": False,
        "distributed": False,
        "modified": False,
        "network_service": True,
    }
    assert doc["license_compatibility"]["summary"]["overall_status"] == "INCOMPATIBLE"

    mit_zip = tmp_path / "all-usage-flags.zip"
    _write_spdx_archive(mit_zip, "MIT", ["ISC"])
    all_flags = _run_cli(
        package, tmp_path, mit_zip,
        "--format", "json",
        "--usage", "commercial,distributed,modified,network_service",
        "--fail-on", "incompatible",
    )
    assert all_flags.returncode == 0, all_flags.stderr
    assert json.loads(all_flags.stdout)["scan"]["usage"] == {
        "commercial": True,
        "distributed": True,
        "modified": True,
        "network_service": True,
    }


def test_asgi_web_api_detects_root_spdx_text_conflict_like_cli(tmp_path, monkeypatch):
    """Audit Finding #2: Web API matches CLI root_conflict UNKNOWN when LICENSE disagrees with package.json."""
    profile = json.loads(
        (ROOT / "application/tests/fixtures/task49-copyleft-licenses.json").read_text(encoding="utf-8"),
    )["licenses"]["GPL-3.0"]
    gpl_bytes = profile["text"].encode("utf-8")
    assert sha256(gpl_bytes).hexdigest() == profile["sha256"]

    zip_path = tmp_path / "web-root-conflict.zip"
    _write_spdx_archive(zip_path, "MIT", ["MIT"])
    members = {}
    with ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            members[name] = zf.read(name)
    members["LICENSE"] = gpl_bytes

    for gateway in _open_zip_gateway(tmp_path, monkeypatch, assessment_and_p2=True):
        session = gateway.register("task58-conflict-user")
        status_url, _ = gateway.upload(session, members, filename="web-root-conflict.zip")
        scan_path = status_url.removesuffix("/status")

        auto_data = _checked(gateway.client.get(scan_path + "/license-compatibility"), 200).json()
        assert auto_data["target"]["license"] is None
        assert auto_data["target"]["source"] == "root_conflict"
        assert auto_data["target"]["status"] == "UNKNOWN"
        assert auto_data["target"]["gaps"] == ["root_spdx_text_conflict"]
        assert auto_data["summary"]["overall_status"] == "UNKNOWN"

        explicit_data = _checked(
            gateway.client.get(scan_path + "/license-compatibility", params={"target_license": "MIT"}),
            200,
        ).json()
        assert explicit_data["target"]["license"] == "MIT"
        assert explicit_data["target"]["source"] == "explicit"
        assert explicit_data["summary"]["overall_status"] == "COMPATIBLE"


def test_target_independent_incompatible_when_target_unresolved(tmp_path):
    """Audit Finding #3: commercial+CC-BY-NC-4.0 and self-contradictory AND fail even when target is UNKNOWN."""
    verdict = evaluate_target_expression(None, "CC-BY-NC-4.0", {"commercial": True})
    assert verdict["status"] == "INCOMPATIBLE"
    assert verdict["rule_id"] == "COMPAT-CC-BY-NC-COMMERCIAL"

    non_comm = evaluate_target_expression(None, "CC-BY-NC-4.0", {"commercial": False})
    assert non_comm["status"] == "UNKNOWN"

    self_bad = evaluate_target_expression(None, "Apache-2.0 AND GPL-2.0-only", {"distributed": True})
    assert self_bad["status"] == "INCOMPATIBLE"
    assert self_bad["rule_id"] == "COMPAT-SELF-INCOMPATIBLE-AND"

    # Even with an otherwise CONDITIONAL target, an internal AND contradiction stays INCOMPATIBLE.
    masked_target = evaluate_target_expression("GPL-2.0-or-later", "Apache-2.0 AND GPL-2.0-only", {"distributed": True})
    assert masked_target["status"] == "INCOMPATIBLE"
    assert masked_target["rule_id"] == "COMPAT-SELF-INCOMPATIBLE-AND"

    package = _package_copy(tmp_path)
    nc_zip = tmp_path / "cc-by-nc-no-root.zip"
    _write_spdx_archive(nc_zip, None, ["CC-BY-NC-4.0"])
    res = _run_cli(package, tmp_path, nc_zip, "--format", "json", "--usage", "commercial", "--fail-on", "incompatible")
    assert res.returncode == 1, res.stderr
    report = json.loads(res.stdout)
    assert report["license_compatibility"]["target"]["license"] is None
    assert report["license_compatibility"]["summary"]["overall_status"] == "INCOMPATIBLE"
    assert report["scan"]["incompatible_count"] == 1

    and_zip = tmp_path / "self-contradicting-and-no-root.zip"
    _write_spdx_archive(and_zip, None, ["Apache-2.0 AND GPL-2.0-only"])
    res_and = _run_cli(package, tmp_path, and_zip, "--format", "json", "--usage", "distributed", "--fail-on", "incompatible")
    assert res_and.returncode == 1, res_and.stderr
    assert json.loads(res_and.stdout)["license_compatibility"]["summary"]["overall_status"] == "INCOMPATIBLE"


def test_pairwise_spdx_and_expression_order_invariance(tmp_path):
    """Audit Finding #4: swapping AND/OR operands produces identical canonical keys, verdicts, and exit codes."""
    assert canonicalize_compatibility_expression("MIT AND GPL-2.0-only") == "GPL-2.0-only AND MIT"
    assert canonicalize_compatibility_expression("GPL-2.0-only AND MIT") == "GPL-2.0-only AND MIT"
    assert canonicalize_compatibility_expression("MIT AND MIT") == "MIT"

    usage = {"distributed": True, "commercial": False}
    for expr1_a, expr1_b in (
        ("MIT AND GPL-2.0-only", "GPL-2.0-only AND MIT"),
        ("Apache-2.0 AND GPL-2.0-only", "GPL-2.0-only AND Apache-2.0"),
    ):
        other = "Apache-2.0 OR GPL-2.0-only"
        v1 = evaluate_pairwise_expressions(expr1_a, other, usage)
        v2 = evaluate_pairwise_expressions(expr1_b, other, usage)
        v3 = evaluate_pairwise_expressions(other, expr1_a, usage)
        v4 = evaluate_pairwise_expressions(other, expr1_b, usage)
        assert v1 == v2 == v3 == v4

    package = _package_copy(tmp_path)
    zip_a = tmp_path / "order-a.zip"
    zip_b = tmp_path / "order-b.zip"
    _write_spdx_archive(zip_a, None, ["MIT AND GPL-2.0-only", "Apache-2.0 OR GPL-2.0-only"])
    _write_spdx_archive(zip_b, None, ["GPL-2.0-only AND MIT", "Apache-2.0 OR GPL-2.0-only"])
    res_a = _run_cli(package, tmp_path, zip_a, "--format", "json", "--usage", "distributed", "--fail-on", "incompatible")
    res_b = _run_cli(package, tmp_path, zip_b, "--format", "json", "--usage", "distributed", "--fail-on", "incompatible")
    assert res_a.returncode == res_b.returncode == 0
    doc_a = json.loads(res_a.stdout)["license_compatibility"]
    doc_b = json.loads(res_b.stdout)["license_compatibility"]
    assert doc_a["matrix"] == doc_b["matrix"]
    assert doc_a["pairwise_conflicts"][0]["status"] == doc_b["pairwise_conflicts"][0]["status"]
    assert doc_a["pairwise_conflicts"][0]["rule_id"] == doc_b["pairwise_conflicts"][0]["rule_id"]


def test_long_normalized_spdx_expression_over_200_chars_returns_200(tmp_path, monkeypatch):
    """Audit Finding #5: valid normalized SPDX expressions > 200 chars must not cause HTTP 500."""
    raw_long = " or ".join([
        "agpl 3.0", "apache 2.0", "bsd 2 clause", "bsd 3 clause", "cc0",
        "cddl 1.0", "epl 2.0", "gpl 2.0", "gpl 2.0 or later", "gpl 3.0",
        "isc", "lgpl 2.1", "lgpl 3.0", "mit", "mpl 2.0", "unlicense",
    ])
    assert len(raw_long) <= 200
    canonical_long = canonicalize_compatibility_expression(raw_long)
    assert 209 <= len(canonical_long) <= 500

    zip_path = tmp_path / "long-spdx.zip"
    _write_spdx_archive(zip_path, "MIT", [raw_long, "GPL-2.0-only"])
    members = {}
    with ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            members[name] = zf.read(name)

    for gateway in _open_zip_gateway(tmp_path, monkeypatch):
        session = gateway.register("task58-long-spdx-user")
        status_url, _ = gateway.upload(session, members, filename="long-spdx.zip")
        scan_path = status_url.removesuffix("/status")
        data = _checked(gateway.client.get(scan_path + "/license-compatibility"), 200).json()
        assert any(item["declared_license"] == canonical_long for item in data["target_assessments"])
        assert canonical_long in data["matrix"]["licenses"]
