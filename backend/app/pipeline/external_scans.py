"""Join fixed external scanners to the existing ZIP facts without guessing ownership."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from app.domain.models import Component, Evidence, HashValue, ProducerRef, ScanError, ScanRun
from app.ingestion import TrustedTreeScan
from app.ingestion.inventory import Inventory
from app.licenses import normalize_license
from app.scanners.external_tools import parse_json_output, run_json_tool
from app.scanners.scancode_pipeline import scan_sealed_tree as scan_licenses
from app.scanners.syft_pipeline import scan_sealed_tree as scan_components


@dataclass
class ExternalScanFacts:
    components: list[Component] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    producers: list[ProducerRef] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)


def collect_external_scans(tree: TrustedTreeScan, inventory: Inventory,
                           clock: Callable[[], datetime]) -> ExternalScanFacts:
    facts = ExternalScanFacts()
    for name, executable, version, scan in (
        ("scancode", "/opt/scancode/venv/bin/scancode", "32.5.0", scan_licenses),
        ("syft", "/opt/syft/syft", "1.51.0", scan_components),
    ):
        try:
            result = run_json_tool(
                executable, ("--version",) if name == "scancode" else ("version", "-o", "json"),
                timeout_seconds=20, max_output_bytes=65536,
                scancode_runtime=name == "scancode", disable_update_check=name == "syft",
            )
            if name == "scancode":
                valid = result.status == "complete" and result.stdout is not None and (
                    result.stdout.decode("utf-8").splitlines()[0] == f"ScanCode version: {version}"
                )
            else:
                payload = parse_json_output(result)
                valid = payload is not None and payload.get("version") == version
            if not valid:
                raise ValueError("unavailable or unexpected scanner version")
            facts.producers.append(ProducerRef(type="scanner", name=name, version=version,
                config_digest=HashValue(algorithm="sha256", value=inventory.root_digest)))
            mapping = scan(tree, inventory, executable=executable, tool_version=version, observed_at=clock()).mapping
            facts.evidence.extend(mapping.evidence)
            if name == "syft":
                facts.components.extend(mapping.components)
        except Exception:
            facts.errors.append(ScanError(code=f"{name}_scan_incomplete", stage="scan",
                message=f"{name} scan could not be completed.", recoverable=True))
    return facts


def merge_external_components(existing: list[Component], incoming: list[Component]) -> list[Component]:
    """Keep manifest IDs and license bindings; join only an unambiguous identity."""
    output = list(existing)
    for item in incoming:
        matches = [index for index, prior in enumerate(output)
                   if (prior.ecosystem, prior.name, prior.version) == (item.ecosystem, item.name, item.version)
                   and (not prior.purl or not item.purl or prior.purl == item.purl)]
        if len(matches) == 1:
            index = matches[0]
            prior = output[index]
            output[index] = prior.model_copy(update={
                "evidence_ids": sorted(set(prior.evidence_ids + item.evidence_ids)),
                "detected_by": sorted(set(prior.detected_by + item.detected_by)),
            })
        else:
            output.append(item)
    return output


def apply_external_licenses(run: ScanRun, facts: ExternalScanFacts) -> ScanRun:
    """File observations remain file observations, never blanket dependency grants."""
    evidence = {item.id: item for item in run.evidence}
    licenses = {item.id: item for item in run.licenses}
    components = []
    for item in run.components:
        if item.license_expression_id is None:
            expression = normalize_license("NOASSERTION", [evidence[key] for key in item.evidence_ids])
            licenses[expression.id] = expression
            item = item.model_copy(update={"license_expression_id": expression.id})
        components.append(item)
    for item in facts.evidence:
        if item.producer.name == "scancode" and item.excerpt:
            expression = normalize_license(item.excerpt, [item])
            licenses[expression.id] = expression
    payload = run.model_dump(mode="python")
    payload.update(components=components, licenses=sorted(licenses.values(), key=lambda item: item.id))
    return ScanRun.model_validate(payload)
