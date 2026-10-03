from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.core.logging import setup_logging
from backend.core.net import force_ipv4
from backend.fetchers.a_index import fetch_a_index
from backend.fetchers.capital import fetch_capital
from backend.fetchers.leaders import fetch_leaders
from backend.fetchers.northbound import fetch_northbound
from backend.fetchers.overseas import fetch_overseas
from backend.fetchers.sector_flow import fetch_sector_flow
from backend.fetchers.sentiment import fetch_sentiment
from backend.services.snapshot import get_or_create

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backend" / "data" / "snapshots"
FRONTEND_DIR = ROOT / "frontend"

DEFAULT_FETCHERS = {
    "overseas": fetch_overseas,
    "a_index": fetch_a_index,
    "sentiment": fetch_sentiment,
    "leaders": fetch_leaders,
    "northbound": fetch_northbound,
    "sector_flow": fetch_sector_flow,
    "capital": fetch_capital,
}


def build_app(data_dir: Path | None = None, fetchers: dict | None = None) -> FastAPI:
    force_ipv4()
    setup_logging(ROOT / "backend" / "data" / "logs")
    app = FastAPI(title="股市脉搏看板")
    _data_dir = Path(data_dir) if data_dir else DATA_DIR
    _fetchers = fetchers if fetchers is not None else DEFAULT_FETCHERS

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    def _raise_if_all_failed(snap):
        if snap["sources"] and all(v == "error" for v in snap["sources"].values()):
            raise HTTPException(status_code=502, detail="全部数据源获取失败")

    @app.get("/api/snapshot")
    def snapshot():
        snap = get_or_create(_fetchers, _data_dir, force=False)
        _raise_if_all_failed(snap)
        return snap

    @app.post("/api/refresh")
    def refresh():
        snap = get_or_create(_fetchers, _data_dir, force=True)
        _raise_if_all_failed(snap)
        return snap

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    return app


app = build_app()
