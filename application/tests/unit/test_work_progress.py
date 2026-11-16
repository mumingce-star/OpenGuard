from __future__ import annotations

import io
import zipfile

from app.ingestion import ZipIngestionService
from app.work_progress import activate, deactivate, get, observe


def _zip(entries: list[tuple[str, bytes]]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


def test_progress_is_event_driven_and_never_moves_without_an_observation() -> None:
    token = activate("scan-a")
    assert get("scan-a") == {"percent": 0, "operation": "扫描已开始"}
    assert get("scan-a") == {"percent": 0, "operation": "扫描已开始"}
    observe(40, "依赖清单解析已完成")
    assert get("scan-a") == {"percent": 40, "operation": "依赖清单解析已完成"}
    observe(25, "过期事件")
    assert get("scan-a") == {"percent": 40, "operation": "过期事件"}
    deactivate("scan-a", token)
    assert get("scan-a") is None


def test_progress_contexts_are_isolated_and_cleanup_does_not_leak() -> None:
    first = activate("scan-a")
    observe(30, "文件清单已建立")
    second = activate("scan-b")
    observe(55, "scancode 扫描已完成")
    assert get("scan-a") == {"percent": 30, "operation": "文件清单已建立"}
    assert get("scan-b") == {"percent": 55, "operation": "scancode 扫描已完成"}
    deactivate("scan-b", second)
    assert get("scan-b") is None
    observe(70, "输入处理与扫描已完成")
    assert get("scan-a") == {"percent": 70, "operation": "输入处理与扫描已完成"}
    deactivate("scan-a", first)
    assert get("scan-a") is None


def test_active_progress_observations_are_bounded_to_128_scans() -> None:
    bindings = [(f"scan-{index}", activate(f"scan-{index}")) for index in range(129)]
    try:
        assert get("scan-0") is None
        assert get("scan-128") == {"percent": 0, "operation": "扫描已开始"}
    finally:
        for scan_id, token in reversed(bindings):
            deactivate(scan_id, token)


def test_zip_ingestion_emits_completed_real_work_milestones(tmp_path) -> None:
    root = tmp_path / "workspaces"
    root.mkdir()
    service = ZipIngestionService(root)
    token = activate("scan-zip")
    during_consumer: dict[str, int | str] | None = None
    try:
        def consume(_session):
            nonlocal during_consumer
            during_consumer = get("scan-zip")

        service.ingest_with_consumer(io.BytesIO(_zip([("requirements.txt", b"demo==1\n")])), consume)
        assert during_consumer == {"percent": 30, "operation": "文件清单已建立"}
        assert get("scan-zip") == {"percent": 40, "operation": "依赖清单解析已完成"}
    finally:
        deactivate("scan-zip", token)
        service.close()
