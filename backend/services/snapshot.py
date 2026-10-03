from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path

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


def _prev_date(data_dir: Path, date: str) -> str | None:
    candidates = []
    for p in Path(data_dir).glob("????-??-??.json"):
        name = p.stem
        if name < date:
            candidates.append(name)
    return max(candidates) if candidates else None


def _attach_turnover_delta(snapshot: dict, data_dir: Path, date: str) -> None:
    section = snapshot.get("a_index")
    if not isinstance(section, dict) or "turnover" not in section:
        return
    turnover = section["turnover"]
    prev = _prev_date(data_dir, date)
    prev_total = None
    if prev is not None:
        prev_snap = load_snapshot(data_dir, prev)
        if prev_snap and isinstance(prev_snap.get("a_index"), dict):
            prev_total = (prev_snap["a_index"].get("turnover") or {}).get("total")
    turnover["prev_total"] = prev_total
    if prev_total is not None and turnover.get("total") is not None:
        turnover["delta"] = round(turnover["total"] - prev_total, 2)
    else:
        turnover["delta"] = None


def build_snapshot(fetchers: dict, data_dir: Path, date: str | None = None) -> dict:
    date = date or _today()
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
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
