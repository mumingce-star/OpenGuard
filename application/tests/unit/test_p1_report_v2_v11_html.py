"""The HTML dependency section and appendix come from the stored Report V2 JSON."""

from copy import deepcopy
from hashlib import sha256
from html import escape, unescape
import json
import re

import pytest

from app.p1.report_v2_html import render_report_html
from app.p1.report_v2_store import ReportV2StoreError
from test_p1_report_v2_v11_integration import (
    SCHEMA, _post, _report_artifacts, _report_path, _zip_members, open_report_gateway,
)
from test_task45_dependency_evidence_real_zip import _checked


def _create_archived_report(harness, case):
    session = harness.register("html_report_owner")
    path, scan = harness.upload(session, _zip_members(case))
    report_path, _ = _report_path(harness, path, scan)
    response = _checked(_post(harness, session, report_path, "same-archive", schema_version="1.1"), 200)
    snapshot = response.json()
    artifacts = _report_artifacts(harness, snapshot)
    return session, snapshot, artifacts


def _observation(document):
    (section,) = [section for section in document["sections"] if section["schema_version"] == SCHEMA]
    return section["content"]


@pytest.mark.parametrize("case", ("completed", "partial", "evidence-gap", "empty"))
def test_downloaded_html_visible_evidence_and_appendix_match_archived_json(open_report_gateway, case):
    with open_report_gateway() as harness:
        _, snapshot, artifacts = _create_archived_report(harness, case)
        document = json.loads(artifacts["json"])
        html = artifacts["html"].decode("utf-8")
        (appendix,) = re.findall(r'<pre id="report-document">(.*?)</pre>', html, re.DOTALL)
        assert json.loads(unescape(appendix)) == document
        visible = html.split('id="report-dependency-evidence"', 1)[1].split('</section>', 1)[0]
        assert "依赖证据" in visible and "扫描覆盖范围未知" in visible
        section = _observation(document)
        assert section["scan_ref"] == snapshot["binding"]["scan_ref"]
        assert ("此处证据不完整" in visible) is section["incomplete"]
        if case == "empty":
            assert "本次扫描未记录可归档的依赖资源" in visible
            assert "Evidence ID" not in visible
        for item in section["items"]:
            for value in (item["name"], item["version"], item["role_state"]):
                if value is not None:
                    assert escape(value, quote=True) in visible
            for ref in item["evidence"]:
                for value in (ref["evidence_id"], ref["source"], ref["file_path"],
                              ref["source_sha256"], ref["verification_status"], ref["producer"]["name"]):
                    if value is not None:
                        assert escape(value, quote=True).casefold() in visible.casefold()
            for gap in item["gaps"]:
                assert escape(gap, quote=True) in visible
        if case == "partial":
            assert "声明侧" in visible and "锁文件侧" in visible and "版本冲突 · confirmed" in visible
            conflict = section["items"][0]["conflicts"][0]
            for key in ("declaration", "lock"):
                side = conflict[key]
                for value in (side["version"], side["resource_id"], side["evidence"][0]["source_sha256"]):
                    assert escape(value, quote=True) in visible
        if case == "evidence-gap":
            assert "50/51" in visible and "evidence_limit_exceeded" in visible


def test_renderer_treats_imported_dependency_text_as_text(open_report_gateway):
    with open_report_gateway() as harness:
        _, _, artifacts = _create_archived_report(harness, "partial")
        document = json.loads(artifacts["json"])
        item = _observation(document)["items"][0]
        item["name"] = 'TEST_ONLY & <literal-evidence> "quoted"'
        html = render_report_html(document).decode("utf-8")
        assert escape(item["name"], quote=True) in html
        assert "<literal-evidence>" not in html
        (appendix,) = re.findall(r'<pre id="report-document">(.*?)</pre>', html, re.DOTALL)
        assert json.loads(unescape(appendix)) == document


@pytest.mark.parametrize("variant", ("missing", "duplicate", "different", "nested"))
def test_store_rejects_html_appendix_disagreement_even_with_matching_raw_digest(open_report_gateway, variant):
    marker = b'<pre id="report-document">'
    with open_report_gateway() as harness:
        session, snapshot, artifacts = _create_archived_report(harness, "empty")
        original = artifacts["html"]
        if variant == "missing":
            changed = original.replace(marker, b"<pre>")
        elif variant == "duplicate":
            changed = original.replace(b"</body>", marker + b"{}</pre></body>")
        elif variant == "nested":
            changed = original.replace(marker, marker + b"<span>nested</span>")
        else:
            start = original.index(marker) + len(marker)
            end = original.index(b"</pre>", start)
            changed = original[:start] + b"{}" + original[end:]
        metadata = deepcopy(snapshot)
        (html_artifact,) = [row for row in metadata["artifacts"] if row["format"] == "html"]
        html_artifact.update(size_bytes=len(changed), content_hash=sha256(changed).hexdigest())
        tenant = harness.gateway.apps[session["user"]["id"]]
        store = tenant.state.report_v2_service.report_store
        with pytest.raises(ReportV2StoreError) as failure:
            store._artifact_payloads(metadata, {**artifacts, "html": changed})
        assert failure.value.code == "invalid_argument"


def test_store_rejects_noncanonical_v11_json_even_when_the_values_match(open_report_gateway):
    with open_report_gateway() as harness:
        session, snapshot, artifacts = _create_archived_report(harness, "empty")
        changed = b" " + artifacts["json"]
        assert json.loads(changed) == json.loads(artifacts["json"])
        metadata = deepcopy(snapshot)
        (json_artifact,) = [row for row in metadata["artifacts"] if row["format"] == "json"]
        json_artifact.update(size_bytes=len(changed), content_hash=sha256(changed).hexdigest())
        tenant = harness.gateway.apps[session["user"]["id"]]
        with pytest.raises(ReportV2StoreError) as failure:
            tenant.state.report_v2_service.report_store._artifact_payloads(metadata, {**artifacts, "json": changed})
        assert failure.value.code == "invalid_argument"
