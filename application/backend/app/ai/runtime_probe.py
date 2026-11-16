"""Explicit, bounded A5-1b runtime reproduction command; never installs Ollama."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

from app.ai.ollama import OllamaProvider
from app.ai.provider import apply_ai_remediations
from app.domain.models import FindingOutcome, ScanRun


_ELIGIBLE_OUTCOMES = frozenset(
    {FindingOutcome.WARNING, FindingOutcome.REVIEW_REQUIRED, FindingOutcome.UNKNOWN}
)
_PRESERVED_FIELDS = (
    "contract_version",
    "id",
    "idempotency_key",
    "status",
    "stage",
    "progress",
    "project",
    "components",
    "ai_assets",
    "licenses",
    "evidence",
    "obligations",
    "summary",
    "report_links",
    "errors",
    "created_at",
    "started_at",
    "finished_at",
)


def _fail() -> int:
    print(
        json.dumps(
            {"error": "ai_runtime_probe_failed"},
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 2


def _deterministic_facts_preserved(before: ScanRun, after: ScanRun) -> bool:
    if any(getattr(before, field) != getattr(after, field) for field in _PRESERVED_FIELDS):
        return False
    if len(before.findings) != len(after.findings):
        return False
    for old, new in zip(before.findings, after.findings, strict=True):
        if old.model_dump(mode="python", exclude={"remediation_id"}) != new.model_dump(
            mode="python", exclude={"remediation_id"}
        ):
            return False
    return True


def run_probe(
    path: Path,
    runs: int,
    provider: object,
    clock=time.monotonic,
    *,
    timeout_seconds: float = 60.0,
) -> dict[str, object]:
    if (
        not isinstance(path, Path)
        or type(runs) is not int
        or not 1 <= runs <= 3
        or type(timeout_seconds) not in {int, float}
        or isinstance(timeout_seconds, bool)
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= 120
        or not callable(clock)
    ):
        raise ValueError
    try:
        run = ScanRun.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        raise ValueError from None

    eligible_ids = {
        finding.id
        for finding in run.findings
        if finding.outcome in _ELIGIBLE_OUTCOMES and finding.remediation_id is None
    }
    if not eligible_ids:
        raise ValueError
    baseline_remediation_ids = {item.id for item in run.remediations}
    durations: list[float] = []
    successes = 0
    identity_sets: list[tuple[tuple[str, str], ...]] = []
    for _ in range(runs):
        started = float(clock())
        if not math.isfinite(started):
            raise ValueError
        result = apply_ai_remediations(  # type: ignore[arg-type]
            run,
            provider,
            timeout_seconds=float(timeout_seconds),
        )
        finished = float(clock())
        if not math.isfinite(finished) or finished < started:
            raise ValueError
        durations.append(round((finished - started) * 1000, 3))

        new_remediations = [
            item for item in result.run.remediations if item.id not in baseline_remediation_ids
        ]
        by_finding = {item.finding_id: item for item in new_remediations}
        if (
            result.status != "generated"
            or len(new_remediations) != len(eligible_ids)
            or set(by_finding) != eligible_ids
            or any(item.verification_status.value != "pending" for item in new_remediations)
            or any(item.generated_by != provider.producer for item in new_remediations)
            or result.run.provenance.ai_enabled is not True
            or result.run.provenance.ai_model != provider.producer
            or provider.producer not in result.run.provenance.tool_versions
            or not _deterministic_facts_preserved(run, result.run)
        ):
            continue
        if any(
            finding.remediation_id
            != (by_finding[finding.id].id if finding.id in eligible_ids else None)
            for finding in result.run.findings
            if finding.id in eligible_ids
        ):
            continue
        identity_sets.append(
            tuple(sorted((item.finding_id, item.id) for item in new_remediations))
        )
        successes += 1

    stable_identity = len(identity_sets) == runs and len(set(identity_sets)) == 1
    return {
        "schema_version": "openguard.ai-runtime-probe/v1",
        "provider": provider.producer.provider,
        "runtime_version": provider.producer.version,
        "model_id": provider.producer.model_id,
        "runs": runs,
        "successes": successes,
        "success_rate": f"{successes}/{runs}",
        "eligible_findings": len(eligible_ids),
        "latency_ms": {
            "cold": durations[0],
            "hot": durations[1:],
            "min": min(durations),
            "median": statistics.median(durations),
            "max": max(durations),
        },
        "validations": {
            "all_pending": successes == runs,
            "producer_bound": successes == runs,
            "deterministic_facts_preserved": successes == runs,
            "stable_identity": stable_identity,
        },
    }


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError from None


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(add_help=False)
    parser.add_argument("scan_run", type=Path)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    try:
        args = parser.parse_args(argv)
        outcome = run_probe(
            args.scan_run,
            args.runs,
            OllamaProvider(),
            timeout_seconds=args.timeout_seconds,
        )
        print(json.dumps(outcome, sort_keys=True, separators=(",", ":")))
        validations = outcome["validations"]
        return 0 if outcome["successes"] == args.runs and all(validations.values()) else 1
    except (Exception, SystemExit):
        return _fail()


if __name__ == "__main__":
    raise SystemExit(main())
