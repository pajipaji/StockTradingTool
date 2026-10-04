import json
from pathlib import Path

from backend.services.snapshot import build_snapshot, load_snapshot, get_or_create


def _ok(name):
    def _f():
        return {"name": name}
    return _f


def _err():
    raise RuntimeError("source down")


def test_isolates_errors(tmp_path: Path):
    snap = build_snapshot({"good": _ok("good"), "bad": _err}, tmp_path, date="2026-10-03")
    assert snap["good"] == {"name": "good"}
    assert "error" in snap["bad"]
    assert snap["sources"]["good"] == "ok"
    assert snap["sources"]["bad"] == "error"
    saved = json.loads((tmp_path / "2026-10-03.json").read_text(encoding="utf-8"))
    assert saved["good"] == {"name": "good"}


def test_all_failed_not_persisted_and_not_cached(tmp_path: Path):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("all down")

    fetchers = {"a_index": boom}
    snap = build_snapshot(fetchers, tmp_path, date="2026-10-03")
    assert snap["sources"] == {"a_index": "error"}
    assert not (tmp_path / "2026-10-03.json").exists()
    assert calls["n"] == 1

    again = get_or_create(fetchers, tmp_path, date="2026-10-03", force=False)
    assert again["sources"]["a_index"] == "error"
    assert calls["n"] == 2


def test_get_or_create_cache_and_force(tmp_path: Path):
    calls = {"n": 0}
    def bump():
        calls["n"] += 1
        return calls["n"]
    fetchers = {"a_index": bump}
    a = get_or_create(fetchers, tmp_path, date="2026-10-03")
    b = get_or_create(fetchers, tmp_path, date="2026-10-03")
    assert a["a_index"] == b["a_index"] == 1
    assert get_or_create(fetchers, tmp_path, date="2026-10-03", force=True)["a_index"] == 2


def test_turnover_delta_uses_prev_snapshot(tmp_path: Path):
    (tmp_path / "2026-09-30.json").write_text(json.dumps({
        "date": "2026-09-30", "sources": {},
        "a_index": {"turnover": {"total": 10500.0, "sh": 1, "sz": 1, "unit": "亿元", "notes": []}},
    }, ensure_ascii=False), encoding="utf-8")

    def index_fetcher():
        return {"turnover": {"total": 12000.0, "sh": 1, "sz": 1, "unit": "亿元", "notes": []}}

    snap = build_snapshot({"a_index": index_fetcher}, tmp_path, date="2026-10-03")
    assert snap["a_index"]["turnover"]["prev_total"] == 10500.0
    assert snap["a_index"]["turnover"]["delta"] == 1500.0


def test_load_missing_returns_none(tmp_path: Path):
    assert load_snapshot(tmp_path, "2020-01-01") is None


def test_sanitizes_non_finite_floats(tmp_path: Path):
    def bad():
        return {"x": float("nan"), "y": float("inf"), "z": float("-inf"), "ok": 1.5}

    snap = build_snapshot({"src": bad}, tmp_path, date="2026-10-03")
    assert snap["src"] == {"x": None, "y": None, "z": None, "ok": 1.5}
    json.dumps(snap, allow_nan=False)

    text = (tmp_path / "2026-10-03.json").read_text(encoding="utf-8")
    assert "NaN" not in text
    assert "Infinity" not in text
    saved = json.loads(text, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    assert saved["src"] == {"x": None, "y": None, "z": None, "ok": 1.5}


def test_turnover_ma(tmp_path):
    import json
    from backend.services.snapshot import build_snapshot
    for i, total in enumerate([100.0, 110.0, 120.0, 130.0, 140.0], start=20):
        d = f"2026-09-{i:02d}"
        (tmp_path / f"{d}.json").write_text(json.dumps(
            {"date": d, "sources": {}, "a_index": {"turnover": {"total": total}}}), encoding="utf-8")
    def idx():
        return {"turnover": {"total": 150.0, "sh": 1, "sz": 1, "unit": "亿元", "notes": []}}
    snap = build_snapshot({"a_index": idx}, tmp_path, date="2026-09-30")
    t = snap["a_index"]["turnover"]
    assert t["prev_total"] == 140.0 and t["delta"] == 10.0
    # 可用总额 [100,110,120,130,140,150] 共6天 -> ma5=mean(110..150)=130.0
    assert t["ma5"] == 130.0
    assert t["ma10"] is None
