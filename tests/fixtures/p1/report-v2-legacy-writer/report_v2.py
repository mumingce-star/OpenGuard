"""A06 immutable Report V2 construction and rendering.

The service reads already-persisted Scan Facts, a fixed Formal Assessment and
explicit Task versions. It never scans, reassesses, calls AI, mutates Tasks, or
changes Formal Assessment state.

Graph inclusion requires an explicitly configured fixed-scan reader and a
matching algorithm version/hash. Notice and Profile remain unavailable;
client-provided hashes never substitute for a source reader.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
from uuid import uuid4

from app.assessment.engine import facts_digest
from app.assessment.store import AssessmentStore, AssessmentStoreError
from app.domain.models import ScanStatus
from app.persistence import (
    SQLiteScanRunRegistry,
    ScanRegistryError,
)

from .models import (
    P1AlgorithmRef,
    P1AssessmentRef,
    P1Binding,
    P1HistoryProvenance,
    P1NoticeRef,
    P1Producer,
    P1ReportArtifact,
    P1ReportV2Snapshot,
    P1ScanRef,
    P1SnapshotSection,
    P1TaskRef,
)
from .remediation_store import (
    RemediationStoreError,
    RemediationTaskStore,
)
from .report_v2_store import (
    ReportV2Store,
    ReportV2StoreError,
)


REPORT_V2_VERSION = "report-v2/1.1"


class ReportV2ServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        reason: str | None = None,
    ):
        self.code = code
        self.reason = reason or code
        super().__init__(self.reason)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest_value(value: object) -> str:
    return _digest(_canonical_bytes(value))


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _report_content_hash(snapshot: dict) -> str:
    value = dict(snapshot)

    # Frozen Contract:
    # Report snapshot hash excludes its own content_hash and artifacts.
    value.pop("content_hash", None)
    value.pop("artifacts", None)

    return _digest_value(value)


def _render_json(document: dict) -> bytes:
    """Render the complete immutable report content.

    This artifact intentionally does not contain the ReportV2Snapshot artifact
    metadata itself, avoiding a self-referential artifact hash.
    """
    return _canonical_bytes(document)


def _render_html(document: dict) -> bytes:
    """Present the same fixed document; never mutate facts or regenerate AI."""
    from .report_v2_html import render_report_html

    return render_report_html(document)


class ReportV2Service:
    def __init__(
        self,
        registry: SQLiteScanRunRegistry,
        assessment_store: AssessmentStore,
        task_store: RemediationTaskStore,
        report_store: ReportV2Store,
        *,
        graph_reader=None,
    ):
        self.registry = registry
        self.assessment_store = assessment_store
        self.task_store = task_store
        self.report_store = report_store
        self.graph_reader = graph_reader

    @staticmethod
    def _scan_ref(
        stored,
        assessment,
    ) -> P1ScanRef:
        run = stored.run

        inventory = run.provenance.inventory_digest

        return P1ScanRef(
            scan_id=run.id,
            revision=run.project.revision,
            facts_hash=assessment.facts_hash,
            input_hash=run.provenance.input_digest.value,
            inventory_hash=(
                inventory.value
                if inventory is not None
                else None
            ),
            status=run.status,
            registry_revision=stored.revision,
        )

    @staticmethod
    def _assessment_ref(
        assessment,
    ) -> P1AssessmentRef:
        return P1AssessmentRef(
            assessment_id=assessment.id,
            version=assessment.version,
            scan_id=assessment.scan_id,
            facts_hash=assessment.facts_hash,
            usage_hash=assessment.usage_hash,
            rule_version=assessment.rule_version,
            formal=True,
        )

    def _fixed_inputs(
        self,
        scan_id: str,
        assessment_id: str,
    ):
        try:
            stored = self.registry.get(scan_id)

        except ScanRegistryError as error:
            if error.code == "registry_not_found":
                raise ReportV2ServiceError(
                    "not_found",
                    reason="scan_not_found",
                ) from error

            if error.code == "registry_invalid_argument":
                raise ReportV2ServiceError(
                    "invalid_argument",
                    reason="scan_id_invalid",
                ) from error

            raise ReportV2ServiceError(
                "upstream_unavailable",
                reason="scan_store_unavailable",
            ) from error

        run = stored.run

        if run.status not in {
            ScanStatus.COMPLETED,
            ScanStatus.PARTIAL,
        }:
            raise ReportV2ServiceError(
                "not_ready",
                reason="scan_not_reportable",
            )

        try:
            assessment = self.assessment_store.get(
                scan_id,
                assessment_id,
            )

            if assessment is None:
                other = self.assessment_store.get_by_id(
                    assessment_id
                )

                if other is not None:
                    raise ReportV2ServiceError(
                        "conflict",
                        reason="assessment_scan_mismatch",
                    )

                raise ReportV2ServiceError(
                    "not_found",
                    reason="assessment_not_found",
                )

        except ReportV2ServiceError:
            raise

        except AssessmentStoreError as error:
            raise ReportV2ServiceError(
                "upstream_unavailable",
                reason="assessment_store_unavailable",
            ) from error

        if assessment.formal is not True:
            raise ReportV2ServiceError(
                "conflict",
                reason="assessment_not_formal",
            )

        if assessment.scan_id != scan_id:
            raise ReportV2ServiceError(
                "conflict",
                reason="assessment_scan_mismatch",
            )

        if assessment.facts_hash != facts_digest(run):
            raise ReportV2ServiceError(
                "conflict",
                reason="facts_hash_mismatch",
            )

        return stored, assessment

    def _task_snapshots(
        self,
        scan_id: str,
        assessment,
        task_refs: list[P1TaskRef],
    ) -> tuple[list[P1TaskRef], list[dict]]:
        normalized = sorted(
            task_refs,
            key=lambda item: (
                item.task_id,
                item.version,
            ),
        )

        task_ids = [
            item.task_id
            for item in normalized
        ]

        if len(task_ids) != len(set(task_ids)):
            raise ReportV2ServiceError(
                "invalid_argument",
                reason="duplicate_task_ref",
            )

        snapshots: list[dict] = []

        for ref in normalized:
            try:
                history = self.task_store.history(
                    ref.task_id
                )

            except RemediationStoreError as error:
                raise ReportV2ServiceError(
                    "upstream_unavailable",
                    reason="task_store_unavailable",
                ) from error

            task = next(
                (
                    item
                    for item in history
                    if item["version"] == ref.version
                ),
                None,
            )

            if task is None:
                raise ReportV2ServiceError(
                    "not_found",
                    reason="task_version_not_found",
                )

            task_assessment = task["assessment_ref"]

            if task["scan_id"] != scan_id:
                raise ReportV2ServiceError(
                    "conflict",
                    reason="task_scan_mismatch",
                )

            if (
                task_assessment["assessment_id"]
                != assessment.id
            ):
                raise ReportV2ServiceError(
                    "conflict",
                    reason="task_assessment_mismatch",
                )

            if (
                task_assessment["version"]
                != assessment.version
                or task_assessment["facts_hash"]
                != assessment.facts_hash
                or task_assessment["usage_hash"]
                != assessment.usage_hash
                or task_assessment["rule_version"]
                != assessment.rule_version
                or task_assessment["formal"] is not True
            ):
                raise ReportV2ServiceError(
                    "conflict",
                    reason="task_binding_mismatch",
                )

            snapshots.append(task)

        return normalized, snapshots

    def _graph_source(self, stored, algorithm_refs):
        """Read only the explicitly selected, server-verified full graph."""
        from .report_v2_graph import ReportGraphError

        if not algorithm_refs:
            return [], None
        if not isinstance(algorithm_refs, list) or not all(
            isinstance(ref, P1AlgorithmRef) for ref in algorithm_refs
        ):
            raise ReportV2ServiceError("invalid_argument", reason="algorithm_reference_invalid")
        kinds = [ref.kind for ref in algorithm_refs]
        if len(kinds) != len(set(kinds)):
            raise ReportV2ServiceError("invalid_argument", reason="duplicate_algorithm_ref")
        if kinds != ["graph"] or self.graph_reader is None:
            raise ReportV2ServiceError(
                "not_ready", reason="observation_snapshot_reader_not_available"
            )
        try:
            reference, graph = self.graph_reader.read(stored, algorithm_refs[0])
        except ReportGraphError as error:
            raise ReportV2ServiceError(error.code, reason=error.reason) from error
        return [reference], graph

    @staticmethod
    def _fingerprint(
        scan_ref: P1ScanRef,
        assessment_ref: P1AssessmentRef,
        task_refs: list[P1TaskRef],
        notice_refs: list[P1NoticeRef],
        algorithm_refs: list[P1AlgorithmRef],
    ) -> str:
        request_value = {
            "schema_version": "1.0",
            "scan_ref": scan_ref.model_dump(
                mode="json"
            ),
            "assessment_ref": assessment_ref.model_dump(
                mode="json"
            ),
            "task_refs": [
                ref.model_dump(mode="json")
                for ref in task_refs
            ],
            "notice_refs": [
                ref.model_dump(mode="json")
                for ref in notice_refs
            ],
            "algorithm_refs": [
                ref.model_dump(mode="json")
                for ref in algorithm_refs
            ],
        }

        return _digest_value(request_value)

    @staticmethod
    def _section(
        *,
        authority: str,
        schema_version: str,
        source_ids: list[str],
        content: object,
        snapshot_ref: str,
    ) -> P1SnapshotSection:
        return P1SnapshotSection(
            authority=authority,
            schema_version=schema_version,
            source_ids=source_ids,
            content_hash=_digest_value(content),
            snapshot_ref=snapshot_ref,
        )

    def create(
        self,
        scan_id: str,
        assessment_id: str,
        *,
        idempotency_key: str,
        task_refs: list[P1TaskRef] | None = None,
        notice_refs: list[P1NoticeRef] | None = None,
        algorithm_refs: list[P1AlgorithmRef] | None = None,
    ) -> P1ReportV2Snapshot:
        if (
            not isinstance(idempotency_key, str)
            or not 1 <= len(idempotency_key) <= 200
            or not idempotency_key.strip()
        ):
            raise ReportV2ServiceError(
                "invalid_argument",
                reason="idempotency_key_invalid",
            )

        task_refs = task_refs or []
        notice_refs = notice_refs or []
        algorithm_refs = algorithm_refs or []

        # Do not trust client-supplied immutable Notice or observation hashes
        # until those source stores/readers are actually available.
        if notice_refs:
            raise ReportV2ServiceError(
                "not_ready",
                reason="notice_snapshot_reader_not_available",
            )

        stored, assessment = self._fixed_inputs(
            scan_id,
            assessment_id,
        )

        scan_ref = self._scan_ref(
            stored,
            assessment,
        )

        assessment_ref = self._assessment_ref(
            assessment
        )

        fixed_task_refs, task_snapshots = (
            self._task_snapshots(
                scan_id,
                assessment,
                task_refs,
            )
        )

        fixed_algorithm_refs, graph_content = self._graph_source(stored, algorithm_refs)

        binding = P1Binding(
            scan_ref=scan_ref,
            assessment_ref=assessment_ref,
            task_refs=fixed_task_refs,
            notice_refs=[],
            algorithm_refs=fixed_algorithm_refs,
        )

        fingerprint = self._fingerprint(
            scan_ref,
            assessment_ref,
            fixed_task_refs,
            [],
            fixed_algorithm_refs,
        )

        snapshot_id = f"rptv2_{uuid4()}"
        created_at = _utc_now()

        base_href = (
            f"/api/v1/scans/{scan_id}"
            f"/assessments/{assessment_id}"
            f"/report-v2/{snapshot_id}"
        )

        scan_content = stored.run.model_dump(
            mode="json"
        )

        assessment_content = assessment.model_dump(
            mode="json"
        )

        workflow_content = {
            "task_refs": [
                ref.model_dump(mode="json")
                for ref in fixed_task_refs
            ],
            "tasks": task_snapshots,
        }

        ai_content = {
            "assessment_id": assessment.id,
            "assessment_version": assessment.version,
            "ai_status": assessment.ai_status,
            "ai_summary": assessment.ai_summary,
            "ai_evidence_ids": list(
                assessment.ai_evidence_ids
            ),
        }

        raw_sections = [
            (
                "scan_facts",
                stored.run.contract_version,
                [scan_id],
                scan_content,
            ),
            (
                "formal_assessment",
                assessment.schema_version,
                [assessment.id],
                assessment_content,
            ),
            (
                "workflow",
                "1.0",
                [
                    ref.task_id
                    for ref in fixed_task_refs
                ],
                workflow_content,
            ),
            (
                "ai_explanation",
                assessment.schema_version,
                [assessment.id],
                ai_content,
            ),
        ]
        if graph_content is not None:
            raw_sections.append((
                "observation", graph_content["schema_version"],
                [graph_content["view_id"]], graph_content,
            ))

        sections: list[P1SnapshotSection] = []
        document_sections: list[dict] = []

        for index, (
            authority,
            schema_version,
            source_ids,
            content,
        ) in enumerate(raw_sections):
            snapshot_ref = (
                f"{base_href}"
                f"?format=json"
                f"#/sections/{index}/content"
            )

            section = self._section(
                authority=authority,
                schema_version=schema_version,
                source_ids=source_ids,
                content=content,
                snapshot_ref=snapshot_ref,
            )

            sections.append(section)

            document_sections.append(
                {
                    **section.model_dump(
                        mode="json"
                    ),
                    "content": content,
                }
            )

        provenance = P1HistoryProvenance(
            producer=P1Producer(
                name="openguard-report-v2",
                version="1.1",
            ),
            source_refs=[scan_ref],
            assessment_refs=[assessment_ref],
            generated_at=created_at,
            algorithm_version=REPORT_V2_VERSION,
            parameters_hash=fingerprint,
        )

        document = {
            "schema_version": "1.0",
            "snapshot_id": snapshot_id,
            "binding": binding.model_dump(
                mode="json"
            ),
            "created_at": created_at,
            "generator_version": REPORT_V2_VERSION,
            "sections": document_sections,
            "provenance": provenance.model_dump(
                mode="json"
            ),
        }

        json_artifact = _render_json(document)
        html_artifact = _render_html(document)

        artifacts = [
            P1ReportArtifact(
                format="html",
                content_hash=_digest(
                    html_artifact
                ),
                size_bytes=len(
                    html_artifact
                ),
                href=(
                    f"{base_href}?format=html"
                ),
            ),
            P1ReportArtifact(
                format="json",
                content_hash=_digest(
                    json_artifact
                ),
                size_bytes=len(
                    json_artifact
                ),
                href=(
                    f"{base_href}?format=json"
                ),
            ),
        ]

        snapshot_value = {
            "schema_version": "1.0",
            "snapshot_id": snapshot_id,
            "binding": binding.model_dump(
                mode="json"
            ),
            "created_at": created_at,
            "generator_version": REPORT_V2_VERSION,
            "sections": [
                section.model_dump(mode="json")
                for section in sections
            ],
            "content_hash": "0" * 64,
            "artifacts": [
                artifact.model_dump(
                    mode="json"
                )
                for artifact in artifacts
            ],
            "provenance": provenance.model_dump(
                mode="json"
            ),
        }

        snapshot_value["content_hash"] = (
            _report_content_hash(
                snapshot_value
            )
        )

        snapshot = (
            P1ReportV2Snapshot.model_validate(
                snapshot_value
            )
        )

        try:
            saved = self.report_store.create(
                scan_id,
                assessment_id,
                idempotency_key,
                fingerprint,
                snapshot.model_dump(
                    mode="json"
                ),
                {
                    "html": html_artifact,
                    "json": json_artifact,
                },
            )

        except ReportV2StoreError as error:
            if error.code in {
                "idempotency_conflict",
                "conflict",
            }:
                raise ReportV2ServiceError(
                    "conflict",
                    reason=error.code,
                ) from error

            if error.code == "invalid_argument":
                raise ReportV2ServiceError(
                    "invalid_argument",
                    reason="report_snapshot_invalid",
                ) from error

            raise ReportV2ServiceError(
                "upstream_unavailable",
                reason=error.code,
            ) from error

        return P1ReportV2Snapshot.model_validate(
            saved
        )

    def get(
        self,
        scan_id: str,
        assessment_id: str,
        snapshot_id: str,
    ) -> P1ReportV2Snapshot | None:
        try:
            value = self.report_store.get(
                scan_id,
                assessment_id,
                snapshot_id,
            )

        except ReportV2StoreError as error:
            raise ReportV2ServiceError(
                "upstream_unavailable",
                reason=error.code,
            ) from error

        if value is None:
            return None

        return P1ReportV2Snapshot.model_validate(
            value
        )

    def artifact(
        self,
        scan_id: str,
        assessment_id: str,
        snapshot_id: str,
        format: str,
    ) -> bytes | None:
        if format not in {"html", "json"}:
            raise ReportV2ServiceError(
                "invalid_argument",
                reason="format_invalid",
            )

        try:
            return self.report_store.get_artifact(
                scan_id,
                assessment_id,
                snapshot_id,
                format,
            )

        except ReportV2StoreError as error:
            if error.code == "invalid_argument":
                raise ReportV2ServiceError(
                    "invalid_argument",
                    reason="format_invalid",
                ) from error

            raise ReportV2ServiceError(
                "upstream_unavailable",
                reason=error.code,
            ) from error