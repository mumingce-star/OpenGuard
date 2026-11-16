"""Offline, TEST-ONLY simulated approvals for the internal two-stage tool.

No test approval here is a real human confirmation or production Evidence.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.api.models import ZipScanCreateFields
from app.api.service import ScanApiService
from app.assessment.engine import canonical_bytes, facts_digest
from app.assessment.service import AssessmentService
from app.assessment.store import AssessmentStore
from app.domain.models import ScanStatus
from app.persistence import SQLiteScanRunRegistry
from app.pipeline.local_zip import build_local_zip_dependency_plan
from app.pipeline.worker import ScanPipelineWorker
from app.p1.models import P1TaskPatchRequest
from app.p1.remediation import RemediationService
from app.p1.remediation_store import RemediationTaskStore
from app.p1.report_v2 import ReportV2Service
from app.p1.report_v2_store import ReportV2Store
from app.reporting import PipelineReportPublisher, ReportArtifactStore
from app.p1 import reviewed_obligation as review
from app.p1 import reviewed_obligation_cli as review_cli
from app.p1.reviewed_obligation_cli import _read_json


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ReviewedObligationHandoffTests(unittest.TestCase):
    def setUp(self):
        # macOS /var is a symlink; the production private-store guard rightly
        # rejects symlink ancestors, so resolve only the test temporary root.
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        self.data.mkdir(mode=0o700)
        self.workspace = self.data / "workspaces"
        self.workspace.mkdir(mode=0o700)
        reports = self.data / "reports"
        reports.mkdir(mode=0o700)
        self.archive = self.root / "tracked-source.zip"
        manifest = (b'[project]\nname = "sample"\nversion = "1.0"\n'
                    b'dependencies = ["pydantic==2.13.4"]\n')
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr("backend/pyproject.toml", manifest)
        self.sdist = self.root / "pydantic-2.13.4.tar.gz"
        self.license = (b"The MIT License (MIT)\nCopyright Pydantic test-only fixture\n"
                        b"Permission granted. Retain the copyright and license notice.\n")
        members = {
            review.LICENSE_MEMBER: self.license,
            review.PACKAGE_MEMBER: (b"[project]\nname = 'pydantic'\nlicense = 'MIT'\n"
                                    b"license-files = ['LICENSE']\n"),
            review.METADATA_MEMBER: (b"Metadata-Version: 2.4\nName: pydantic\nVersion: 2.13.4\n"
                                     b"License-Expression: MIT\nLicense-File: LICENSE\n\n"),
        }
        with tarfile.open(self.sdist, "w:gz") as output:
            for name, raw in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                output.addfile(info, io.BytesIO(raw))
        self.patches = [
            patch.object(review, "SOURCE_ARCHIVE_SHA256", _sha(self.archive.read_bytes())),
            patch.object(review, "ARTIFACT_SHA256", _sha(self.sdist.read_bytes())),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

        self.db = self.data / "scans.db"
        registry = SQLiteScanRunRegistry(self.db)
        service = ScanApiService(registry)
        accepted, created = service.create_zip_scan(
            ZipScanCreateFields(source_type="zip"), staged_name=self.archive.name,
            project_name="sample", input_digest=_sha(self.archive.read_bytes()),
        )
        self.assertTrue(created)
        self.source_id = accepted.scan_id
        plan = build_local_zip_dependency_plan(
            self.archive, self.workspace, clock=lambda: datetime.now(timezone.utc),
        )
        stored = ScanPipelineWorker(
            registry, terminal_publisher=PipelineReportPublisher(ReportArtifactStore(reports)).publish,
        ).run(self.source_id, plan)
        self.assertIn(stored.run.status, {ScanStatus.COMPLETED, ScanStatus.PARTIAL})
        self.assertEqual(stored.run.obligations, [])
        self.old = stored.run.model_dump(mode="json")
        source_assessments = AssessmentStore(self.data / "assessment.db")
        source_service = AssessmentService(registry, source_assessments)
        source_service.initialize()
        source_service.on_terminal(stored.run)
        self.source_assessment = source_assessments.latest(self.source_id)
        self.assertIsNotNone(self.source_assessment)
        source_tasks = RemediationTaskStore(self.data / "remediation.db")
        source_tasks.initialize()
        source_reports = ReportV2Store(self.data / "report_v2.db")
        source_reports.initialize()
        source_report_service = ReportV2Service(registry, source_assessments, source_tasks, source_reports)
        self.source_report = source_report_service.create(
            self.source_id, self.source_assessment.id, idempotency_key="original-report",
            task_refs=[], notice_refs=[],
        )
        self.source_report_bytes = {format: source_report_service.artifact(
            self.source_id, self.source_assessment.id, self.source_report.snapshot_id, format,
        ) for format in ("json", "html")}
        registry.close()
        self.card = review.prepare(self.db, self.source_id, self.archive, self.sdist)

    def _confirmation(self):
        return {
            "schema": "openguard.reviewed-obligation-confirmation/1",
            "card_sha256": self.card["card_sha256"],
            "source_scan_id": self.source_id,
            "resource_id": self.card["resource_id"],
            "resource_version": "2.13.4",
            "artifact_sha256": self.card["artifact_sha256"],
            "license_sha256": self.card["license_sha256"],
            "scope": "runtime_dependency",
            "reviewer_self_reported": "TEST ONLY simulated reviewer",
            "confirmed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "license_text_reviewed_in_full": True,
            "license_applies_to_exact_artifact": True,
            "scope_confirmed": True,
            "applicability_basis": "TEST ONLY: exact sdist member and fixed-version project declaration checked.",
            "scope_basis": "TEST ONLY: project.dependencies is a runtime dependency declaration.",
            "limits_acknowledged": True,
        }

    def _apply(self, record, *, expected_hash=None):
        return review.apply(self.data, self.archive, self.sdist, self.card, record,
                            expected_confirmation_sha256=expected_hash or review.confirmation_hash(self.card, record))

    def test_prepare_is_pending_and_read_only(self):
        before = {p.name: _sha(p.read_bytes()) for p in self.data.iterdir() if p.is_file()}
        card = review.prepare(self.db, self.source_id, self.archive, self.sdist)
        after = {p.name: _sha(p.read_bytes()) for p in self.data.iterdir() if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(card["state"], "pending")
        self.assertEqual(card["resource_version"], "2.13.4")
        self.assertEqual(card["license_sha256"], _sha(self.license))
        self.assertNotIn("confirmation", card)

    def test_missing_or_wrong_confirmation_fails_before_new_scan(self):
        initial = SQLiteScanRunRegistry(self.db)
        rows = initial.list_runs(limit=100).items
        initial.close()
        for field, wrong, code in (("card_sha256", "0" * 64, "confirmation_binding_mismatch"),
                                   ("source_scan_id", "scn_wrong", "confirmation_binding_mismatch"),
                                   ("resource_version", "2.13.5", "confirmation_binding_mismatch"),
                                   ("artifact_sha256", "0" * 64, "confirmation_binding_mismatch"),
                                   ("license_sha256", "0" * 64, "confirmation_binding_mismatch"),
                                   ("scope", "project_code", "confirmation_binding_mismatch"),
                                   ("license_text_reviewed_in_full", False, "confirmation_incomplete"),
                                   ("confirmed_at", [], "confirmation_time_invalid"),
                                   ("applicability_basis", [], "confirmation_incomplete")):
            record = self._confirmation()
            record[field] = wrong
            own_hash = _sha(canonical_bytes(record))
            with self.subTest(field=field), self.assertRaises(review.ReviewAdmissionError) as caught:
                self._apply(record, expected_hash=own_hash)
            self.assertEqual(caught.exception.code, code)
            current = SQLiteScanRunRegistry(self.db)
            self.assertEqual(len(current.list_runs(limit=100).items), len(rows))
            current.close()
            self.assertFalse((self.data / "reviewed-obligation").exists())
        record = self._confirmation()
        with self.assertRaises(review.ReviewAdmissionError) as caught:
            self._apply(record, expected_hash="0" * 64)
        self.assertEqual(caught.exception.code, "confirmation_hash_mismatch")
        final = SQLiteScanRunRegistry(self.db)
        self.assertEqual(len(final.list_runs(limit=100).items), len(rows))
        final.close()
        self.assertFalse((self.data / "reviewed-obligation").exists())

    def test_sdist_path_swap_after_hash_cannot_change_parsed_license(self):
        changed = self.root / "changed.tar.gz"
        with tarfile.open(self.sdist, "r:gz") as original, tarfile.open(changed, "w:gz") as target:
            for member in original.getmembers():
                stream = original.extractfile(member)
                self.assertIsNotNone(stream)
                raw = stream.read()
                if member.name == review.LICENSE_MEMBER:
                    raw = b"TEST ONLY DIFFERENT LICENSE CONTENT"
                member.size = len(raw)
                target.addfile(member, io.BytesIO(raw))
        alternate = changed.read_bytes()
        original_open = tarfile.open

        def swap_then_open(*args, **kwargs):
            self.sdist.write_bytes(alternate)
            return original_open(*args, **kwargs)

        with patch.object(tarfile, "open", side_effect=swap_then_open):
            self.assertEqual(review._license_bytes(self.sdist), self.license)

    def test_material_growth_during_read_is_rejected_by_actual_byte_limit(self):
        material = self.root / "growing.bin"
        material.write_bytes(b"1234")
        original_fstat = os.fstat
        expanded = False

        def grow_after_stat(descriptor):
            nonlocal expanded
            info = original_fstat(descriptor)
            if not expanded:
                expanded = True
                material.write_bytes(b"12345")
            return info

        with patch.object(review.os, "fstat", side_effect=grow_after_stat):
            with self.assertRaises(review.ReviewAdmissionError) as caught:
                review._bounded_file_bytes(material, limit=4)
        self.assertEqual(caught.exception.code, "material_unsafe")

    def test_source_zip_path_swap_before_manifest_read_uses_verified_bytes(self):
        changed = self.root / "changed-manifest.zip"
        with zipfile.ZipFile(changed, "w") as output:
            output.writestr("backend/pyproject.toml", b'[project]\nname="other"\nversion="1"\n')
        alternate = changed.read_bytes()
        original_reader = review._read_member

        def swap_before_member(archive, member, *, maximum):
            self.archive.write_bytes(alternate)
            return original_reader(archive, member, maximum=maximum)

        prepared_at = datetime.fromisoformat(self.card["prepared_at"].replace("Z", "+00:00"))
        with patch.object(review, "_read_member", side_effect=swap_before_member):
            self.assertEqual(review.prepare(self.db, self.source_id, self.archive, self.sdist,
                                            now=prepared_at), self.card)

    def test_source_zip_path_swap_before_scan_uses_verified_bytes(self):
        changed = self.root / "changed-source.zip"
        with zipfile.ZipFile(changed, "w") as output:
            output.writestr("backend/pyproject.toml", b'[project]\nname="other"\nversion="1"\n')
        alternate = changed.read_bytes()
        from app.pipeline import local_zip
        original_plan = local_zip.build_local_zip_dependency_plan

        def swap_before_plan(path, workspace_root, **kwargs):
            self.archive.write_bytes(alternate)
            return original_plan(path, workspace_root, **kwargs)

        with patch.object(local_zip, "build_local_zip_dependency_plan", side_effect=swap_before_plan):
            result = self._apply(self._confirmation())
        registry = SQLiteScanRunRegistry(self.db)
        self.assertEqual(registry.get(result["new_scan_id"]).run.provenance.input_digest.value,
                         self.card["source_input_sha256"])
        self.assertEqual(registry.get(self.source_id).run.model_dump(mode="json"), self.old)
        registry.close()

    def test_material_change_and_ambiguous_resource_rejected(self):
        tampered = self.root / "tampered.tar.gz"
        tampered.write_bytes(self.sdist.read_bytes() + b"changed")
        with self.assertRaisesRegex(review.ReviewAdmissionError, "artifact_hash_mismatch"):
            review.prepare(self.db, self.source_id, self.archive, tampered)
        registry = SQLiteScanRunRegistry(self.db)
        source = registry.get(self.source_id).run
        registry.close()
        duplicate = source.components[0].model_copy(update={"id": "cmp_" + str(__import__("uuid").uuid4()),
                                                      "name": "pydantic", "version": "2.13.5"})
        ambiguous = source.model_copy(update={"components": [*source.components, duplicate]})
        with patch.object(review, "_read_source", return_value=ambiguous):
            with self.assertRaisesRegex(review.ReviewAdmissionError, "resource_ambiguous_or_version_mismatch"):
                review.prepare(self.db, self.source_id, self.archive, self.sdist)

    def test_operator_confirmation_file_must_be_private(self):
        path = self.root / "operator.json"
        path.write_text(json.dumps(self._confirmation()), encoding="utf-8")
        path.chmod(0o644)
        with self.assertRaisesRegex(review.ReviewAdmissionError, "review_input_unsafe"):
            _read_json(path)
        path.chmod(0o600)
        self.assertEqual(_read_json(path)["source_scan_id"], self.source_id)

    def test_simulated_confirmation_uses_original_rules_and_consumers(self):
        # Explicitly synthetic approval input; no real-world verified claim.
        record = self._confirmation()
        result = self._apply(record)
        self.assertNotEqual(result["source_scan_id"], result["new_scan_id"])
        self.assertTrue(result["obligations"])
        self.assertTrue(result["task_refs"])
        self.assertEqual(set(result["artifacts"]), {"json", "html"})
        self.assertTrue(all(value["href"].startswith("/api/v1/") for value in result["artifacts"].values()))
        confirmation_path = self.data / "reviewed-obligation" / (
            "confirmation-" + result["confirmation_sha256"] + ".json")
        self.assertEqual(_sha(confirmation_path.read_bytes()), result["confirmation_sha256"])
        registry = SQLiteScanRunRegistry(self.db)
        old = registry.get(self.source_id).run
        new = registry.get(result["new_scan_id"]).run
        self.assertEqual(old.model_dump(mode="json"), self.old)
        self.assertEqual(old.obligations, [])
        self.assertEqual(AssessmentStore(self.data / "assessment.db").get(
            self.source_id, self.source_assessment.id), self.source_assessment)
        self.assertTrue(any(item.rule_id for item in new.obligations))
        self.assertTrue(all(set(item.source_evidence_ids).issubset({evidence.id for evidence in new.evidence})
                            for item in new.obligations))
        self.assertEqual(facts_digest(new), result["facts_hash"])
        assessment_store = AssessmentStore(self.data / "assessment.db")
        assessment = assessment_store.latest(new.id)
        self.assertIsNotNone(assessment)
        self.assertTrue(assessment.formal)
        self.assertTrue(assessment.obligations)
        self.assertTrue(all(item.fulfillment == "pending" for item in assessment.obligations))
        task_store = RemediationTaskStore(self.data / "remediation.db")
        task = result["task_refs"][0]
        before = task_store.get(new.id, assessment.id, task["task_id"])
        patched = RemediationService(registry, assessment_store, task_store).patch(
            new.id, assessment.id, task["task_id"],
            P1TaskPatchRequest(expected_version=before["version"], status="done", note="TEST ONLY workflow action"),
        )
        self.assertEqual(patched.status, "done")
        self.assertEqual(registry.get(new.id).run.obligations, new.obligations)
        self.assertEqual(assessment_store.get(new.id, assessment.id).obligations, assessment.obligations)
        before_dismiss = task_store.get(new.id, assessment.id, task["task_id"])
        dismissed = RemediationService(registry, assessment_store, task_store).patch(
            new.id, assessment.id, task["task_id"],
            P1TaskPatchRequest(expected_version=before_dismiss["version"], status="dismissed",
                               note="TEST ONLY workflow action"),
        )
        self.assertEqual(dismissed.status, "dismissed")
        self.assertEqual(assessment_store.get(new.id, assessment.id).obligations, assessment.obligations)
        report_store = ReportV2Store(self.data / "report_v2.db")
        report = ReportV2Service(registry, assessment_store, task_store, report_store)
        for format, expected in self.source_report_bytes.items():
            self.assertEqual(report.artifact(self.source_id, self.source_assessment.id,
                                             self.source_report.snapshot_id, format), expected)
        prior_bytes = {path.name: _sha(path.read_bytes()) for path in self.data.iterdir() if path.is_file()}
        for format in ("json", "html"):
            raw = report.artifact(new.id, assessment.id, result["report_snapshot_id"], format)
            self.assertEqual(_sha(raw), result["artifacts"][format]["sha256"])
            self.assertEqual(raw, report.artifact(new.id, assessment.id, result["report_snapshot_id"], format))
        self.assertEqual(prior_bytes, {path.name: _sha(path.read_bytes()) for path in self.data.iterdir()
                                       if path.is_file()})
        with self.assertRaisesRegex(review.ReviewAdmissionError, "confirmation_replay"):
            self._apply(record)
        registry.close()
        restored_registry = SQLiteScanRunRegistry(self.db)
        restored_report = ReportV2Service(
            restored_registry, AssessmentStore(self.data / "assessment.db"),
            RemediationTaskStore(self.data / "remediation.db"), ReportV2Store(self.data / "report_v2.db"),
        )
        for format in ("json", "html"):
            raw = restored_report.artifact(new.id, assessment.id, result["report_snapshot_id"], format)
            self.assertEqual(_sha(raw), result["artifacts"][format]["sha256"])
        restored_registry.close()


class ReviewedObligationCliResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "private"
        self.private.mkdir(mode=0o700)
        self.result = self.private / "result.json"

    def _main(self, result=None):
        args = ["apply", "--data-dir", str(self.root), "--source-archive", str(self.root / "source.zip"),
                "--artifact", str(self.root / "artifact.tar.gz"), "--card", str(self.root / "card.json"),
                "--confirmation", str(self.root / "confirmation.json"),
                "--confirmation-sha256", "a" * 64, "--result", str(result or self.result)]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = review_cli.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_existing_result_refused_before_apply_and_preserved(self):
        self.result.write_bytes(b"prior result must stay unchanged")
        with patch.object(review_cli, "apply") as operation, patch.object(review_cli, "_read_json", return_value={}):
            code, _, stderr = self._main()
        self.assertEqual(code, 2)
        self.assertIn("result", stderr)
        operation.assert_not_called()
        self.assertEqual(self.result.read_bytes(), b"prior result must stay unchanged")

    def test_unsafe_result_parent_refused_before_apply(self):
        unsafe = self.root / "unsafe"
        unsafe.mkdir(mode=0o755)
        with patch.object(review_cli, "apply") as operation, patch.object(review_cli, "_read_json", return_value={}):
            code, _, stderr = self._main(unsafe / "result.json")
        self.assertEqual(code, 2)
        self.assertIn("result", stderr)
        operation.assert_not_called()
        self.assertFalse((unsafe / "result.json").exists())

    def test_success_result_has_explicit_state(self):
        value = {"schema": "test-only-result", "new_scan_id": "scn_test_only"}
        with patch.object(review_cli, "apply", return_value=value) as operation, patch.object(
                review_cli, "_read_json", return_value={}):
            code, stdout, stderr = self._main()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), value)
        self.assertEqual(json.loads(self.result.read_bytes()), {"state": "success", "result": value})
        operation.assert_called_once()

    def test_apply_failure_records_failure_without_retry(self):
        with (patch.object(review_cli, "apply", side_effect=review.ReviewAdmissionError("test_only_failure")) as operation,
              patch.object(review_cli, "_read_json", return_value={})):
            code, _, stderr = self._main()
        self.assertEqual(code, 2)
        self.assertIn("test_only_failure", stderr)
        self.assertEqual(json.loads(self.result.read_bytes()),
                         {"state": "failure", "error": "test_only_failure", "retry_apply": False})
        operation.assert_called_once()
        prior = self.result.read_bytes()
        with patch.object(review_cli, "apply") as replay, patch.object(review_cli, "_read_json", return_value={}):
            code, _, stderr = self._main()
        self.assertEqual(code, 2)
        self.assertIn("result_exists", stderr)
        replay.assert_not_called()
        self.assertEqual(self.result.read_bytes(), prior)

    def test_result_write_failure_after_apply_reports_completed_no_retry(self):
        value = {"schema": "test-only-result", "new_scan_id": "scn_test_only"}
        with (patch.object(review_cli, "apply", return_value=value) as operation,
              patch.object(review_cli, "_read_json", return_value={}),
              patch.object(review_cli, "_finalize_result", side_effect=OSError("TEST ONLY write failure"))):
            code, _, stderr = self._main()
        self.assertEqual(code, 2)
        self.assertIn("apply_completed_result_unavailable", stderr)
        self.assertEqual(json.loads(self.result.read_bytes())["state"], "pending")
        operation.assert_called_once()


if __name__ == "__main__":
    unittest.main()
