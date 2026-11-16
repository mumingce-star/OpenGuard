"""Focused offline adapter tests; all positive transport receipts are synthetic.

The historical-input case reads only two explicitly selected saved files. It
does not authenticate old transport, upgrade source status, or operate M1.
Run directly with --case test_synthetic_observation_preserves_exact_draft for
the single positive Fail-first target. --xml writes the actual unittest result.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
SPEC = importlib.util.spec_from_file_location(
    "draft66_fixture_support", ROOT / "tests/support/draft66_fixture_support.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("pinned draft66 fixture support is unavailable")
SUPPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SUPPORT)

try:
    ADAPTER = importlib.import_module("app.p2.npm_source_draft_adapter")
except ModuleNotFoundError as exc:
    if exc.name != "app.p2.npm_source_draft_adapter":
        raise
    ADAPTER = None

HISTORICAL_INPUTS: Path | None = None
ASSOCIATION = "SAME_METADATA_BYTES_NOT_SAME_ACQUISITION_EVENT"
URL = "https://registry.npmjs.org/is-number/7.0.0"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def synthetic_transport(body, observed_at=None):
    """A mock verifier fixture, never evidence of an actual network response."""
    return dict(
        request_method="GET", request_url=URL, final_url=URL, redirect_count=0,
        timed_out=False, transport_policy_id="SYNTHETIC_OFFLINE_TEST_POLICY",
        response_bytes=len(body), response_sha256=sha(body), http_status=200,
        observed_at=observed_at or datetime(2026, 10, 18, 5, 0, tzinfo=timezone.utc),
        synthetic_proof={"fixture_only": True, "labels": ["mock", "not_real_transport"]},
    )


class AdapterTests(unittest.TestCase):
    def require_adapter(self):
        self.assertTrue(
            ADAPTER is not None and callable(getattr(ADAPTER, "adapt_npm_source_draft", None)),
            "new internal adapter is absent on the frozen parent")

    def call(self, *, claim=None, blobs=None, body=None, receipt=None,
             verifier=None, pins=None, indices=(0, 1, 2, 3, 4)):
        self.require_adapter()
        default_claim, default_blobs = SUPPORT.fixture()
        c = default_claim if claim is None else claim
        b = default_blobs if blobs is None else blobs
        raw = b["metadata"] if body is None else body
        transport = synthetic_transport(raw) if receipt is None else receipt
        verify = (lambda _receipt: True) if verifier is None else verifier
        return ADAPTER.adapt_npm_source_draft(
            body=raw, transport_receipt=transport, verify_attestation=verify,
            claim=SUPPORT.enc(c) if isinstance(c, dict) else c,
            pins=SUPPORT.repin(b) if pins is None else pins,
            blobs=b, event_indices=indices,
        )

    def reject(self, code, **kwargs):
        self.require_adapter()
        with self.assertRaises(ValueError) as caught:
            self.call(**kwargs)
        self.assertEqual(getattr(caught.exception, "code", str(caught.exception)), code)
        if code.startswith("ADAPTER_"):
            self.assertIsInstance(caught.exception, ADAPTER.AdapterError)

    def direct_draft(self, claim, blobs):
        self.assertIsNotNone(SUPPORT.MOD, "frozen existing draft validator is absent")
        return SUPPORT.MOD.validate_draft(
            SUPPORT.enc(claim), pins=SUPPORT.repin(blobs), blobs=blobs,
            event_indices=(0, 1, 2, 3, 4))

    def assert_boundaries(self, result):
        self.assertEqual(result["association"], ASSOCIATION)
        self.assertEqual(result["data_scope"], "TEST_ONLY")
        self.assertEqual(result["formal_effect"], "none")
        self.assertIs(result["m1_complete"], False)
        self.assertIs(result["historical_receipt_authenticated"], False)
        draft = result["historical_draft"]
        self.assertEqual(draft["new_fact_count"], 0)
        self.assertEqual(draft["positive_advice"], [])
        self.assertEqual(draft["formal_effect"], "none")
        self.assertIs(draft["public_contract_approved"], False)
        self.assertIs(draft["m1_complete"], False)
        self.assertIn("A_TRUSTED_ISSUANCE_MISSING", draft["gaps"])
        self.assertIn("OWNER_APPLICABILITY_SIGNATURE_MISSING", draft["gaps"])
        self.assertIn("HISTORICAL_OBSERVATION_NOT_NEW_FACT", draft["gaps"])

    def test_synthetic_observation_preserves_exact_draft(self):
        self.require_adapter()
        c, b = SUPPORT.fixture()
        expected = self.direct_draft(c, b)
        result = self.call(claim=c, blobs=b)
        self.assertEqual(result["historical_draft"], expected)
        self.assertEqual(result["transport_observation"]["state"], "official_metadata_observed")
        self.assertEqual(result["transport_observation"]["response_sha256"], sha(b["metadata"]))
        self.assertEqual(result["transport_observation"]["transport_policy_id"],
                         "SYNTHETIC_OFFLINE_TEST_POLICY")
        self.assertEqual(expected["retrieval_method"], "UNKNOWN_IN_PINNED_RECEIPT")
        self.assertIn("HISTORICAL_METHOD_NOT_RECORDED", expected["gaps"])
        self.assert_boundaries(result)

    def test_deterministic_and_inputs_not_mutated(self):
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        before = copy.deepcopy((c, b, r))
        one = self.call(claim=c, blobs=b, receipt=r)
        two = self.call(claim=c, blobs=b, receipt=r)
        self.assertEqual(one, two)
        self.assertEqual((c, b, r), before)

    def test_missing_timeout_is_not_invented(self):
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        del r["timed_out"]
        self.reject("npm_transport_timeout_invalid", claim=c, blobs=b, receipt=r)
        self.assertNotIn("timed_out", r)

    def test_timeout_requires_exact_boolean(self):
        for value in (None, 0, 1, "false", [], {}):
            with self.subTest(value=repr(value)):
                c, b = SUPPORT.fixture()
                r = synthetic_transport(b["metadata"])
                r["timed_out"] = value
                self.reject("npm_transport_timeout_invalid", claim=c, blobs=b, receipt=r)

    def test_timeout_failure_cannot_return_successful_draft(self):
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        r["timed_out"] = True
        self.reject("ADAPTER_TRANSPORT_NOT_OBSERVED", claim=c, blobs=b, receipt=r)

    def test_http_failure_cannot_return_successful_draft(self):
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        r["http_status"] = 503
        self.reject("ADAPTER_TRANSPORT_NOT_OBSERVED", claim=c, blobs=b, receipt=r)

    def test_verifier_must_return_exact_true(self):
        for value in (False, None, 1, "true", {}):
            with self.subTest(value=repr(value)):
                self.reject("npm_transport_unverified", verifier=lambda _r, v=value: v)

    def test_verifier_exception_is_bounded_failure(self):
        def fail(_receipt):
            raise RuntimeError("SYNTHETIC PRIVATE FAILURE TEXT")
        self.reject("npm_transport_unverified", verifier=fail)

    def test_verifier_receipt_mutation_is_rejected(self):
        mutations = {
            "status": lambda r: r.update(http_status=201),
            "time": lambda r: r.update(observed_at=datetime(2026, 10, 19, tzinfo=timezone.utc)),
            "url": lambda r: r.update(request_url="https://example.invalid/"),
            "policy": lambda r: r.update(transport_policy_id="CHANGED"),
            "hash": lambda r: r.update(response_sha256="0" * 64),
            "nested": lambda r: r["synthetic_proof"]["labels"].append("CHANGED"),
            "typed_equal": lambda r: r["synthetic_proof"].update(fixture_only=1),
        }
        for label, mutate in mutations.items():
            with self.subTest(mutation=label):
                c, b = SUPPORT.fixture()
                r = synthetic_transport(b["metadata"])
                before = copy.deepcopy(r)
                def verify(passed):
                    mutate(passed)
                    return True
                self.reject("ADAPTER_VERIFIER_MUTATED_RECEIPT", claim=c, blobs=b,
                            receipt=r, verifier=verify)
                self.assertEqual(r, before)

    def test_mutation_then_callback_exception_keeps_mutation_code(self):
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        before = copy.deepcopy(r)
        def verify(passed):
            passed["http_status"] = 201
            raise RuntimeError("SYNTHETIC callback failed after mutation")
        self.reject("ADAPTER_VERIFIER_MUTATED_RECEIPT", claim=c, blobs=b,
                    receipt=r, verifier=verify)
        self.assertEqual(r, before)

    def test_callback_closure_cannot_retarget_frozen_blobs(self):
        c, b = SUPPORT.fixture()
        before = copy.deepcopy((c, b))
        expected = self.direct_draft(c, b)
        r = synthetic_transport(b["metadata"])
        def verify(_passed):
            # This intentional test callback side effect is not adapter I/O or
            # evidence that arbitrary callbacks cannot cause external effects.
            b["metadata"] = b"SYNTHETIC external callback changed caller mapping"
            c["usage"]["commercial"] = True
            return True
        result = self.call(claim=c, blobs=b, receipt=r, verifier=verify)
        self.assertEqual(result["historical_draft"], expected)
        self.assertEqual(result["transport_observation"]["response_sha256"],
                         sha(before[1]["metadata"]))
        self.assertNotEqual((c, b), before)
        self.assert_boundaries(result)

    def test_custom_copy_hook_is_never_invoked(self):
        hook_calls = []
        class Custom:
            def __deepcopy__(self, _memo):
                hook_calls.append("CALLED")
                raise AssertionError("custom copying must not occur")
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        r["synthetic_proof"]["custom"] = Custom()
        self.reject("ADAPTER_INPUT_INVALID", claim=c, blobs=b, receipt=r)
        self.assertEqual(hook_calls, [])

    def test_same_json_different_metadata_bytes_do_not_link(self):
        c, b = SUPPORT.fixture()
        body = b["metadata"] + b"\n"
        self.assertEqual(json.loads(body), json.loads(b["metadata"]))
        self.reject("ADAPTER_METADATA_BYTES_MISMATCH", claim=c, blobs=b,
                    body=body, receipt=synthetic_transport(body))

    def test_different_metadata_declaration_does_not_rewrite_legacy(self):
        c, b = SUPPORT.fixture()
        changed = json.loads(b["metadata"])
        changed["license"] = "SYNTHETIC_CHANGED_DECLARATION"
        body = SUPPORT.enc(changed)
        before = copy.deepcopy(b)
        self.reject("ADAPTER_METADATA_BYTES_MISMATCH", claim=c, blobs=b,
                    body=body, receipt=synthetic_transport(body))
        self.assertEqual(b, before)

    def test_transport_target_rejection_is_propagated(self):
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        r["final_url"] = "https://example.invalid/"
        self.reject("npm_transport_target_mismatch", claim=c, blobs=b, receipt=r)

    def test_transport_size_and_hash_rejections_are_propagated(self):
        for field, value, code in (
            ("response_bytes", 1, "npm_transport_size_mismatch"),
            ("response_sha256", "0" * 64, "npm_response_hash_mismatch"),
        ):
            with self.subTest(field=field):
                c, b = SUPPORT.fixture()
                r = synthetic_transport(b["metadata"])
                r[field] = value
                self.reject(code, claim=c, blobs=b, receipt=r)

    def test_invalid_metadata_rejections_are_propagated(self):
        bodies = (
            (b'{"name":"is-number","name":"is-number","version":"7.0.0"}',
             "npm_duplicate_json_key"),
            (b'{"name":"other","version":"7.0.0"}', "npm_wrong_package"),
            (b'{"name":"is-number","version":"7.0.1"}', "npm_wrong_version"),
        )
        for body, code in bodies:
            with self.subTest(code=code):
                self.reject(code, body=body, receipt=synthetic_transport(body))

    def test_strict_transport_is_checked_before_invalid_draft_claim(self):
        c, b = SUPPORT.fixture()
        r = synthetic_transport(b["metadata"])
        del r["timed_out"]
        self.reject("npm_transport_timeout_invalid", claim=b"not JSON", blobs=b, receipt=r)

    def test_wrong_binding_uses_existing_draft_rejection(self):
        c, b = SUPPORT.fixture()
        c["binding"]["assessment_version"] = 2
        self.reject("DRAFT_HISTORY_BINDING_MISMATCH", claim=c, blobs=b)

    def test_wrong_pin_uses_existing_draft_rejection(self):
        c, b = SUPPORT.fixture()
        pins = list(SUPPORT.repin(b))
        kind, size, digest = pins[0]
        pins[0] = kind, size + 1, digest
        self.reject("DRAFT_ARTIFACT_PIN_MISMATCH", claim=c, blobs=b, pins=tuple(pins))

    def test_historical_result_hash_rejection_is_not_masked(self):
        c, b = SUPPORT.fixture()
        SUPPORT.update_json(b, "history", lambda x: x[4]["response"]["result"].update(
            result_sha256="0" * 64))
        self.reject("DRAFT_PRIOR_RESULT_HASH_MISMATCH", claim=c, blobs=b)

    def test_archive_integrity_rejection_is_not_masked(self):
        c, b = SUPPORT.fixture()
        SUPPORT.update_json(b, "metadata", lambda x: x["dist"].update(integrity="sha512-invalid"))
        SUPPORT.update_json(b, "receipts", lambda x: x[0]["metadata"].update(
            bytes=len(b["metadata"]), sha256=sha(b["metadata"])))
        self.reject("DRAFT_NPM_INTEGRITY_MISMATCH", claim=c, blobs=b)

    def test_revoked_source_and_scope_are_not_upgraded(self):
        c, b = SUPPORT.fixture()
        c["source_status"] = "revoked"
        c["owner_scope_status"] = "revoked"
        result = self.call(claim=c, blobs=b)
        self.assertEqual(result["historical_draft"], self.direct_draft(c, b))
        self.assertIn("SOURCE_REVOKED", result["historical_draft"]["gaps"])
        self.assertIn("OWNER_SCOPE_REVOKED", result["historical_draft"]["gaps"])
        self.assert_boundaries(result)

    def test_explicit_synthetic_usage_does_not_create_advice(self):
        c, b = SUPPORT.fixture()
        c["usage"]["distributed"] = True
        def update_history(history):
            history[2]["response"]["usage"]["distributed"] = True
            result = history[4]["response"]["result"]
            result["usage"]["distributed"] = True
            result["result_sha256"] = sha(SUPPORT.enc({
                key: value for key, value in result.items() if key != "result_sha256"}))
        SUPPORT.update_json(b, "history", update_history)
        result = self.call(claim=c, blobs=b)
        self.assertIs(result["historical_draft"]["usage"]["distributed"], True)
        self.assert_boundaries(result)

    def test_observation_times_remain_separate_without_rewriting_history(self):
        for observed in (
            datetime(2026, 10, 10, tzinfo=timezone.utc),
            datetime(2026, 10, 11, 4, 20, tzinfo=timezone.utc),
            datetime(2026, 10, 18, tzinfo=timezone.utc),
        ):
            with self.subTest(observed=observed.isoformat()):
                c, b = SUPPORT.fixture()
                before = copy.deepcopy(b)
                expected = self.direct_draft(c, b)
                result = self.call(claim=c, blobs=b,
                                   receipt=synthetic_transport(b["metadata"], observed))
                self.assertEqual(result["transport_observation"]["observed_at"], observed.isoformat())
                self.assertEqual(result["historical_draft"], expected)
                self.assertEqual(result["historical_draft"]["metadata"]["utc"],
                                 "2026-10-11T04:20:00+00:00")
                self.assertEqual(b, before)
                self.assert_boundaries(result)

    def test_no_file_network_process_effects_inside_adapter(self):
        c, b = SUPPORT.fixture()
        receipt = synthetic_transport(b["metadata"])
        with patch("builtins.open", side_effect=AssertionError("unexpected file I/O")), \
             patch.object(socket, "socket", side_effect=AssertionError("unexpected network")), \
             patch.object(subprocess, "Popen", side_effect=AssertionError("unexpected process")):
            result = self.call(claim=c, blobs=b, receipt=receipt)
        self.assert_boundaries(result)

    def test_saved_legacy_receipt_is_rejected_without_field_backfill(self):
        if HISTORICAL_INPUTS is None:
            self.skipTest("explicit historical-inputs directory not supplied")
        # These are saved ordinary evidence files, not a live source or DB.
        metadata = (HISTORICAL_INPUTS / "metadata.json").read_bytes()
        receipt_bytes = (HISTORICAL_INPUTS / "receipts.json").read_bytes()
        records = json.loads(receipt_bytes)
        matches = [record for record in records if record.get("package") == "is-number"
                   and record.get("version") == "7.0.0"]
        self.assertEqual(len(matches), 1)
        legacy = matches[0]["metadata"]
        self.assertNotIn("timed_out", legacy)
        self.assertEqual(legacy["sha256"], sha(metadata))
        before = copy.deepcopy(legacy)
        verifier_calls = []
        def verify(_receipt):
            verifier_calls.append("UNEXPECTED")
            return True
        self.reject("npm_transport_target_mismatch", body=metadata, receipt=legacy,
                    verifier=verify)
        self.assertEqual(verifier_calls, [])
        self.assertEqual(legacy, before)
        self.assertEqual((HISTORICAL_INPUTS / "receipts.json").read_bytes(), receipt_bytes)


class RecordedResult(unittest.TextTestResult):
    """Record actual test outcomes; subtest errors retain unittest semantics."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self.active = None

    def startTest(self, test):
        self.active = {"id": test.id(), "start": time.perf_counter(), "events": []}
        super().startTest(test)

    def addFailure(self, test, err):
        self.active["events"].append(("failure", self._exc_info_to_string(err, test)))
        super().addFailure(test, err)

    def addError(self, test, err):
        self.active["events"].append(("error", self._exc_info_to_string(err, test)))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.active["events"].append(("skipped", reason))
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            tag = "failure" if issubclass(err[0], test.failureException) else "error"
            self.active["events"].append((tag, str(subtest) + "\n" + "".join(traceback.format_exception(*err))))
        super().addSubTest(test, subtest, err)

    def stopTest(self, test):
        self.active["elapsed"] = time.perf_counter() - self.active["start"]
        self.rows.append(self.active)
        self.active = None
        super().stopTest(test)


def write_xml(path, result):
    suite = ET.Element("testsuite", name="p2-npm-source-draft-adapter", tests=str(result.testsRun),
                       failures=str(len(result.failures)), errors=str(len(result.errors)),
                       skipped=str(len(result.skipped)))
    for row in result.rows:
        classname, name = row["id"].rsplit(".", 1)
        case = ET.SubElement(suite, "testcase", classname=classname, name=name,
                             time="%.6f" % row["elapsed"])
        for tag, detail in row["events"]:
            ET.SubElement(case, tag).text = detail
    target = Path(path)
    if target.exists():
        raise FileExistsError("refusing to overwrite existing JUnit")
    with target.open("xb") as output:
        ET.ElementTree(suite).write(output, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", default=[], help="exact method name, repeatable")
    parser.add_argument("--xml", help="new output file for the actual JUnit result")
    parser.add_argument("--historical-inputs", type=Path)
    args = parser.parse_args()
    global HISTORICAL_INPUTS
    HISTORICAL_INPUTS = args.historical_inputs
    if args.case:
        suite = unittest.TestSuite(AdapterTests(name) for name in args.case)
    else:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(AdapterTests)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
    if args.xml:
        write_xml(args.xml, result)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
