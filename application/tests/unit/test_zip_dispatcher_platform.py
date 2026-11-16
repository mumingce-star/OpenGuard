"""The optional durable dispatcher must import on Windows and fail closed."""

import pytest

from app.pipeline import zip_dispatcher


def test_missing_posix_lock_capability_fails_before_touching_storage(monkeypatch):
    monkeypatch.setattr(zip_dispatcher, "fcntl", None)
    dispatcher = object.__new__(zip_dispatcher.ZipDispatcher)
    with pytest.raises(zip_dispatcher.ZipDispatcherError) as error:
        dispatcher._acquire_lifecycle_lock()
    assert error.value.code == "dispatch_unsupported_platform"
