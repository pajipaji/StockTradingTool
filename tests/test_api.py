from pathlib import Path
from fastapi.testclient import TestClient

from backend.app import build_app


def test_snapshot_and_refresh(tmp_path: Path):
    calls = {"n": 0}
    def counting():
        calls["n"] += 1
        return {"n": calls["n"]}

    client = TestClient(build_app(data_dir=tmp_path, fetchers={"a_index": counting}))
    assert client.get("/healthz").json() == {"ok": True}
    assert client.get("/api/snapshot").json()["a_index"] == {"n": 1}
    assert client.get("/api/snapshot").json()["a_index"] == {"n": 1}   # 缓存
    assert client.post("/api/refresh").json()["a_index"] == {"n": 2}
    assert calls["n"] == 2


def test_all_sources_failed_returns_502(tmp_path: Path):
    def boom():
        raise RuntimeError("down")
    client = TestClient(build_app(data_dir=tmp_path, fetchers={"a_index": boom}))
    assert client.get("/api/snapshot").status_code == 502
