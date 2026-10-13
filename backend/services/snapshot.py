from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path

from backend.core import fetch as fetch_core
from backend.core.logging import get_logger

logger = get_logger("snapshot")


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _today() -> str:
    return dt.date.today().isoformat()


def _attach_turnover_delta(snapshot: dict, data_dir: Path, date: str) -> None:
    section = snapshot.get("a_index")
    if not isinstance(section, dict) or not isinstance(section.get("turnover"), dict):
        return
    turnover = section["turnover"]
    totals = []
    recent = [p for p in sorted(Path(data_dir).glob("????-??-??.json")) if p.stem < date][-10:]
    for p in recent:
        snap = load_snapshot(data_dir, p.stem)
        t = ((snap or {}).get("a_index") or {}).get("turnover") or {}
        if isinstance(t, dict) and t.get("total") is not None:
            totals.append(t["total"])
    cur = turnover.get("total")
    series = totals + ([cur] if cur is not None else [])
    turnover["prev_total"] = totals[-1] if totals else None
    turnover["delta"] = round(cur - totals[-1], 2) if (cur is not None and totals) else None
    turnover["ma5"] = round(sum(series[-5:]) / 5, 2) if len(series) >= 5 else None
    turnover["ma10"] = round(sum(series[-10:]) / 10, 2) if len(series) >= 10 else None


def build_snapshot(fetchers: dict, data_dir: Path, date: str | None = None) -> dict:
    date = date or _today()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    fetch_core.reset_cache()
    snapshot = {
        "date": date,
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": {},
    }
    for name, fn in fetchers.items():
        try:
            snapshot[name] = fn()
            snapshot["sources"][name] = "ok"
        except Exception as exc:
            logger.error("fetcher %s failed: %s", name, exc)
            snapshot[name] = {"error": str(exc)}
            snapshot["sources"][name] = "error"
    _attach_turnover_delta(snapshot, data_dir, date)
    snapshot = _sanitize(snapshot)
    if snapshot["sources"] and all(v == "error" for v in snapshot["sources"].values()):
        logger.error("all sources failed; not persisting snapshot for %s", date)
        return snapshot
    target = data_dir / f"{date}.json"
    tmp = data_dir / f".{date}.json.tmp"
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return snapshot


def load_snapshot(data_dir: Path, date: str) -> dict | None:
    path = Path(data_dir) / f"{date}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_or_create(fetchers: dict, data_dir: Path, date: str | None = None, force: bool = False) -> dict:
    date = date or _today()
    if not force:
        cached = load_snapshot(data_dir, date)
        if cached is not None:
            return cached
    return build_snapshot(fetchers, data_dir, date)
