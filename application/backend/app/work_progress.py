"""Ephemeral, event-driven scan workflow progress."""

from __future__ import annotations

from collections import OrderedDict
from contextvars import ContextVar, Token
from threading import RLock

_ACTIVE_SCAN_ID: ContextVar[str | None] = ContextVar("active_scan_id", default=None)
_PROGRESS: OrderedDict[str, dict[str, int | str]] = OrderedDict()
_LOCK = RLock()
_MAX_ACTIVE_SCANS = 128
_RECORDERS: dict[str, _PhaseRecorder] = {}
_PHASES = ('ingestion','inventory','scan','normalize','rules','ai_assist','report')

class _PhaseRecorder:
    def __init__(self, scan_id, observer):
        self.scan_id, self.observer = scan_id, observer
        self.index, self.closed, self.percent = -1, False, 0
    def emit(self, phase, state):
        try:
            self.observer(self.scan_id, phase, state, self.percent)
        except Exception:
            pass  # Optional observation cannot change scan/result semantics.
    def stage(self, phase, state='start', percent=0):
        if phase not in _PHASES or state not in {'start','end'}:
            return
        index = _PHASES.index(phase)
        self.percent = max(self.percent, min(99, max(0, percent)))
        if index < self.index:
            return  # Coarse pipeline repeats checks already completed in ingestion.
        if index > self.index:
            if self.index >= 0 and not self.closed:
                self.emit(_PHASES[self.index], 'end')
            self.index, self.closed = index, False
            self.emit(phase, 'start')
        if state == 'end' and not self.closed:
            self.emit(phase, 'end'); self.closed = True
    def finish(self, status, percent):
        if self.index < 0 or status not in {'completed','partial','failed','cancelled'}:
            return
        self.percent = max(self.percent, min(100, max(0, percent)))
        if status == 'completed' and not self.closed:
            self.emit(_PHASES[self.index], 'end'); self.closed = True
        self.emit(_PHASES[self.index], status)



def activate(scan_id: str, observer=None) -> Token[str | None] | None:
    if type(scan_id) is not str or not scan_id:
        return None
    try:
        with _LOCK:
            _PROGRESS[scan_id] = {"percent": 0, "operation": "扫描已开始"}
            _PROGRESS.move_to_end(scan_id)
            while len(_PROGRESS) > _MAX_ACTIVE_SCANS:
                old, _ = _PROGRESS.popitem(last=False)
                _RECORDERS.pop(old, None)
            if callable(observer):
                recorder = _PhaseRecorder(scan_id, observer)
                _RECORDERS[scan_id] = recorder
                recorder.stage('ingestion')
        return _ACTIVE_SCAN_ID.set(scan_id)
    except Exception:
        return None


def deactivate(scan_id: str, token: Token[str | None] | None) -> None:
    try:
        with _LOCK:
            _PROGRESS.pop(scan_id, None)
            _RECORDERS.pop(scan_id, None)
    except Exception:
        pass
    if token is not None:
        try:
            _ACTIVE_SCAN_ID.reset(token)
        except Exception:
            pass


def observe(percent: int, operation: str, *, phase: str | None = None, event: str = 'start') -> None:
    """Record a real-work milestone and never interfere with the scan."""
    try:
        scan_id = _ACTIVE_SCAN_ID.get()
        if scan_id is None or type(percent) is not int or type(operation) is not str:
            return
        with _LOCK:
            prior = _PROGRESS.get(scan_id)
            if prior is None:
                return
            _PROGRESS[scan_id] = {
                "percent": max(int(prior["percent"]), min(99, max(0, percent))),
                "operation": operation,
            }
            _PROGRESS.move_to_end(scan_id)
            recorder = _RECORDERS.get(scan_id)
            if recorder is not None:
                recorder.percent = max(recorder.percent, int(_PROGRESS[scan_id]["percent"]))
                if phase is not None:
                    recorder.stage(phase, event, recorder.percent)
    except Exception:
        return


def get(scan_id: str) -> dict[str, int | str] | None:
    try:
        with _LOCK:
            value = _PROGRESS.get(scan_id)
            return dict(value) if value is not None else None
    except Exception:
        return None


def finish(status: str, percent: int) -> None:
    try:
        with _LOCK:
            recorder = _RECORDERS.get(_ACTIVE_SCAN_ID.get())
            if recorder is not None:
                recorder.finish(status, percent)
    except Exception:
        pass
