"""Ephemeral, event-driven scan workflow progress."""

from __future__ import annotations

from collections import OrderedDict
from contextvars import ContextVar, Token
from threading import RLock

_ACTIVE_SCAN_ID: ContextVar[str | None] = ContextVar("active_scan_id", default=None)
_PROGRESS: OrderedDict[str, dict[str, int | str]] = OrderedDict()
_LOCK = RLock()
_MAX_ACTIVE_SCANS = 128


def activate(scan_id: str) -> Token[str | None] | None:
    if type(scan_id) is not str or not scan_id:
        return None
    try:
        with _LOCK:
            _PROGRESS[scan_id] = {"percent": 0, "operation": "扫描已开始"}
            _PROGRESS.move_to_end(scan_id)
            while len(_PROGRESS) > _MAX_ACTIVE_SCANS:
                _PROGRESS.popitem(last=False)
        return _ACTIVE_SCAN_ID.set(scan_id)
    except Exception:
        return None


def deactivate(scan_id: str, token: Token[str | None] | None) -> None:
    try:
        with _LOCK:
            _PROGRESS.pop(scan_id, None)
    except Exception:
        pass
    if token is not None:
        try:
            _ACTIVE_SCAN_ID.reset(token)
        except Exception:
            pass


def observe(percent: int, operation: str) -> None:
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
    except Exception:
        return


def get(scan_id: str) -> dict[str, int | str] | None:
    try:
        with _LOCK:
            value = _PROGRESS.get(scan_id)
            return dict(value) if value is not None else None
    except Exception:
        return None
