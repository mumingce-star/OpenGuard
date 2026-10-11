"""Offline audit of existing P2B observations; no HTTP, service or database access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.p2.contract import strict_json
from app.p2b.materials import MAX_MATERIAL_BYTES
from app.p2b.offline_material_audit import audit_existing_material

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="复用现有P2 TEST_ONLY材料观察进行只读离线核对")
    parser.add_argument("--closure", type=Path, default=ROOT / "docs/p2/p2b-evidence-closure.json")
    parser.add_argument("--is-number-license", type=Path, help="已取得的本地原字节；不抓取，不上传正文")
    args = parser.parse_args()
    closure = strict_json(args.closure.read_bytes())
    readback = strict_json((ROOT / "tests/fixtures/p2b/three-scan-readback.json").read_bytes())
    results = {case["case_id"]: case["p2"]["after"] for case in readback["cases"]}
    raw = None
    if args.is_number_license is not None:
        with args.is_number_license.open("rb") as stream:
            raw = stream.read(MAX_MATERIAL_BYTES + 1)
    rows = [audit_existing_material(case, result_payload=results[case["case_id"]],
                                   content=raw if case["resource"]["name"] == "is-number" else None)
            for case in closure["cases"]]
    print(json.dumps({"kind": "openguard.p2b.offline-material-audit-batch/1",
                      "overall": "PARTIAL", "new_facts": 0, "cases": rows},
                     ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
