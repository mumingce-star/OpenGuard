"""Bind persisted reports to the ScanRun committed by the pipeline."""

from __future__ import annotations

from app.domain.models import ReportFormat, ScanRun, ScanStatus
from app.reporting.store import ReportArtifactStore


_REPORTABLE = frozenset({ScanStatus.COMPLETED, ScanStatus.PARTIAL})


class ReportPipelineError(RuntimeError):
    """Stable, non-sensitive terminal report publication failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise ReportPipelineError(code) from None


class PipelineReportPublisher:
    """Publish every P0 format before the terminal ScanRun CAS becomes visible."""

    def __init__(self, store: ReportArtifactStore) -> None:
        if type(store) is not ReportArtifactStore:
            _fail("report_pipeline_invalid_argument")
        self._store = store

    def publish(self, run: ScanRun) -> ScanRun:
        if type(run) is not ScanRun or run.status not in _REPORTABLE or run.report_links:
            _fail("report_pipeline_invalid_argument")
        try:
            links = [self._store.publish(run, report_format) for report_format in ReportFormat]
            if [link.format for link in links] != list(ReportFormat):
                raise ValueError
            payload = run.model_dump(mode="python")
            payload["report_links"] = links
            return ScanRun.model_validate(payload)
        except ReportPipelineError:
            raise
        except Exception:
            _fail("report_pipeline_publish_failed")
        raise AssertionError("unreachable")


__all__ = ["PipelineReportPublisher", "ReportPipelineError"]
