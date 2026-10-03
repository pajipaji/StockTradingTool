# 股市脉搏看板 实现计划（v2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 akshare 构建本地"股市脉搏"每日复盘看板：FastAPI 后端抓取 7 个板块生成每日快照，深色盘面风前端分 3 屏用 ECharts 展示（含情绪博弈、概念主线、申万 Treemap 热图、涨跌分布直方图）。

**Architecture:** akshare → 网络抓取层(强制 IPv4/限速/重试/缓存) → 7 个 Fetcher 输出标准化 dict → 快照服务组装 + 错误隔离 + 量能增减(对比上一快照) + 原子写 → FastAPI `/api/snapshot`、`/api/refresh` → 原生 HTML/CSS/JS + 本地 ECharts 渲染 3 屏。

**Tech Stack:** Python 3.9.6、akshare 1.18.88、pandas、FastAPI、uvicorn、pytest、原生前端 + ECharts。

**Spec:** `docs/superpowers/specs/2026-10-03-stock-dashboard-design.md`（v2）

## Global Constraints

- Python 3.9.6（`/usr/bin/python3`）；akshare 固定 **1.18.88**；pandas 已装。
- **所有** akshare 调用必须经过 `backend/core/fetch.py::fetch()`。
- 应用启动最早期必须调用 `force_ipv4()`。
- 涨跌幅统一**百分比数值**（`1.2` = 1.2%）；金额统一**亿元**（`round(x,2)`）；同花顺资金流本就是亿元，不再换算。
- 缺失值 `None`/`null`；异常分区 `{"error": "<message>"}`。
- 版本控制：本目录未初始化 git；**除非用户明确要求，否则不执行任何 git commit/push**。每个任务完成检查点 = 指定测试通过（不提交）。
- 视觉令牌（前端逐字使用）：`--bg:#0e1117; --panel:#161b26; --panel-2:#1e2430; --border:#2a3141; --text:#e6e9ef; --text-muted:#8b93a7; --up:#ff4d4f; --down:#22c55e; --flat:#8b93a7; --accent:#3b82f6; --gold:#f5c451;`
- 走势图固定近 **60** 日；北向固定近 **30** 日。
- 不做历史快照浏览（无日期参数、无 `/api/dates`、无日期下拉）。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `backend/core/logging.py` | 日志初始化 |
| `backend/core/net.py` | `force_ipv4()` |
| `backend/core/ratelimit.py` | `RateLimiter` |
| `backend/core/retry.py` | `retry()` |
| `backend/core/fetch.py` | `fetch()` 统一入口 |
| `backend/core/units.py` | `to_yi` / `pct` |
| `backend/fetchers/overseas.py` | 外围风向（美股/期指/港股/费半/汇率） |
| `backend/fetchers/a_index.py` | A股指数/量能/涨跌分布 |
| `backend/fetchers/sentiment.py` | 情绪博弈（涨跌停/炸板/连板/晋级） |
| `backend/fetchers/northbound.py` | 北向资金 |
| `backend/fetchers/sw_industry.py` | 申万一级（含涨跌家数） |
| `backend/fetchers/sector_flow.py` | 概念 + 同花顺行业资金流 |
| `backend/fetchers/capital.py` | 主力资金/融资融券（best-effort） |
| `backend/services/snapshot.py` | 组装/错误隔离/量能增减/原子写 |
| `backend/app.py` | FastAPI 路由 + 静态托管 |
| `frontend/index.html` / `style.css` / `app.js` / `vendor/echarts.min.js` | 前端 3 屏 |
| `tests/…` | 分层测试 |
| `run.sh` / `README.md` / `requirements.txt` / `pytest.ini` | 运行与配置 |

---

## Task 1: 项目脚手架与日志

**Files:**
- Create: `backend/__init__.py`, `backend/core/__init__.py`, `backend/fetchers/__init__.py`, `backend/services/__init__.py`
- Create: `backend/core/logging.py`
- Create: `requirements.txt`
- Test: `tests/test_logging.py`

**Interfaces:**
- Produces: `setup_logging(log_dir: Path, level: int = logging.INFO) -> None`；`get_logger(name: str) -> logging.Logger`。

- [ ] **Step 1: 创建目录与包文件**

```bash
mkdir -p backend/core backend/fetchers backend/services backend/data/snapshots backend/data/cache backend/data/logs frontend/vendor tests/fixtures docs/superpowers/plans
touch backend/__init__.py backend/core/__init__.py backend/fetchers/__init__.py backend/services/__init__.py
```

- [ ] **Step 2: 写 `requirements.txt`**

```
akshare==1.18.88
pandas>=2.0.0
fastapi>=0.110
uvicorn[standard]>=0.27
pytest>=7.4
```

- [ ] **Step 3: 写失败测试 `tests/test_logging.py`**

```python
import logging
from pathlib import Path
from backend.core.logging import setup_logging, get_logger


def test_setup_logging_writes_file(tmp_path: Path):
    setup_logging(tmp_path, level=logging.INFO)
    log = get_logger("test.logger")
    log.info("hello-dashboard")
    for h in logging.getLogger().handlers:
        h.flush()
    content = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "hello-dashboard" in content
```

- [ ] **Step 4: 运行测试确认失败**

Run: `python3 -m pytest tests/test_logging.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 5: 实现 `backend/core/logging.py`**

```python
import logging
from pathlib import Path

_CONFIGURED = False


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)
    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python3 -m pytest tests/test_logging.py -v`
Expected: PASS

---

## Task 2: 强制 IPv4

**Files:**
- Create: `backend/core/net.py`
- Test: `tests/test_net.py`

**Interfaces:**
- Produces: `force_ipv4() -> bool`（首次 True，重复幂等返回 False）。

- [ ] **Step 1: 写失败测试 `tests/test_net.py`**

```python
import socket
from backend.core.net import force_ipv4


def test_force_ipv4_filters_ipv6(monkeypatch):
    def fake(host, port, *args, **kwargs):
        return [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 0, 0, 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ]
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert force_ipv4() is True
    results = socket.getaddrinfo("example.com", 443)
    assert all(r[0] == socket.AF_INET for r in results)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_net.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/core/net.py`**

```python
import socket

_ORIGINAL = None
_APPLIED = False


def force_ipv4() -> bool:
    """只解析 IPv4，规避东财 IPv6 出口被 RST。幂等。"""
    global _ORIGINAL, _APPLIED
    if _APPLIED:
        return False
    _ORIGINAL = socket.getaddrinfo

    def _ipv4_only(host, *args, **kwargs):
        results = _ORIGINAL(host, *args, **kwargs)
        ipv4 = [r for r in results if r[0] == socket.AF_INET]
        return ipv4 or results

    socket.getaddrinfo = _ipv4_only
    _APPLIED = True
    return True
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_net.py -v`
Expected: PASS

---

## Task 3: 限速器

**Files:**
- Create: `backend/core/ratelimit.py`
- Test: `tests/test_ratelimit.py`

**Interfaces:**
- Produces: `RateLimiter(min_interval=0.8, clock=time.monotonic, sleeper=time.sleep)`；`wait(source) -> None`。

- [ ] **Step 1: 写失败测试 `tests/test_ratelimit.py`**

```python
from backend.core.ratelimit import RateLimiter


def test_sleeps_when_too_fast():
    now = {"t": 100.0}
    slept = []
    def clock():
        return now["t"]
    def sleeper(seconds):
        slept.append(seconds)
        now["t"] += seconds
    rl = RateLimiter(min_interval=1.0, clock=clock, sleeper=sleeper)
    rl.wait("sina")
    assert slept == []
    now["t"] += 0.3
    rl.wait("sina")
    assert slept and abs(slept[-1] - 0.7) < 1e-6


def test_independent_per_source():
    slept = []
    rl = RateLimiter(min_interval=1.0, clock=lambda: 0.0, sleeper=slept.append)
    rl.wait("a"); rl.wait("b")
    assert slept == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_ratelimit.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/core/ratelimit.py`**

```python
import time


class RateLimiter:
    def __init__(self, min_interval: float = 0.8, clock=time.monotonic, sleeper=time.sleep):
        self.min_interval = float(min_interval)
        self._clock = clock
        self._sleep = sleeper
        self._last = {}

    def wait(self, source: str) -> None:
        if self.min_interval <= 0:
            self._last[source] = self._clock()
            return
        now = self._clock()
        last = self._last.get(source)
        if last is not None:
            remaining = self.min_interval - (now - last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last[source] = now
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_ratelimit.py -v`
Expected: PASS

---

## Task 4: 重试装饰器

**Files:**
- Create: `backend/core/retry.py`
- Test: `tests/test_retry.py`

**Interfaces:**
- Produces: `retry(times=3, base_delay=1.0, jitter=0.5, exceptions=(Exception,), sleeper=time.sleep, logger=None)`。

- [ ] **Step 1: 写失败测试 `tests/test_retry.py`**

```python
import pytest
from backend.core.retry import retry


def test_succeeds_after_failures():
    calls = {"n": 0}
    delays = []

    @retry(times=3, base_delay=1.0, jitter=0.0, sleeper=delays.append)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
    assert delays == [1.0, 2.0]


def test_raises_after_exhaustion():
    @retry(times=2, base_delay=0.0, jitter=0.0, sleeper=lambda s: None)
    def always_fail():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        always_fail()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_retry.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/core/retry.py`**

```python
import functools
import random
import time


def retry(times: int = 3, base_delay: float = 1.0, jitter: float = 0.5,
          exceptions=(Exception,), sleeper=time.sleep, logger=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(times):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if attempt == times - 1:
                        raise
                    delay = base_delay * (2 ** attempt) + random.uniform(0, jitter)
                    if logger is not None:
                        logger.warning("retry %s/%s %s: %s", attempt + 1, times, func.__name__, exc)
                    sleeper(delay)
        return wrapper
    return decorator
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_retry.py -v`
Expected: PASS

---

## Task 5: 统一抓取入口

**Files:**
- Create: `backend/core/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Produces: `fetch(fn, *args, source: str, use_cache: bool = True, **kwargs)`；模块级 `LIMITER`、`RETRY_TIMES`、`reset_cache()`。

- [ ] **Step 1: 写失败测试 `tests/test_fetch.py`**

```python
import backend.core.fetch as fetchmod
from backend.core.fetch import fetch
from backend.core.ratelimit import RateLimiter


def setup_function(_):
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_returns_and_caches():
    calls = {"n": 0}
    def fake():
        calls["n"] += 1
        return {"v": calls["n"]}

    a = fetch(fake, source="sina")
    b = fetch(fake, source="sina")
    assert a == b == {"v": 1}
    assert fetch(fake, source="sina", use_cache=False) == {"v": 2}


def test_retries_until_success(monkeypatch):
    monkeypatch.setattr(fetchmod, "RETRY_TIMES", 3)
    monkeypatch.setattr(fetchmod.time, "sleep", lambda s: None)
    state = {"n": 0}
    def flaky():
        state["n"] += 1
        if state["n"] < 2:
            raise ValueError("x")
        return "ok"
    assert fetch(flaky, source="x", use_cache=False) == "ok"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetch.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/core/fetch.py`**

```python
import os
import time

from backend.core.ratelimit import RateLimiter
from backend.core.retry import retry

LIMITER = RateLimiter(float(os.environ.get("DASHBOARD_MIN_INTERVAL", "0.8")))
RETRY_TIMES = int(os.environ.get("DASHBOARD_RETRY_TIMES", "3"))
_CACHE = {}


def reset_cache() -> None:
    _CACHE.clear()


def _key(fn, args, kwargs):
    return (getattr(fn, "__module__", ""), getattr(fn, "__name__", str(fn)), args, tuple(sorted(kwargs.items())))


def fetch(fn, *args, source: str, use_cache: bool = True, **kwargs):
    key = _key(fn, args, kwargs)
    if use_cache and key in _CACHE:
        return _CACHE[key]
    LIMITER.wait(source)
    runner = retry(times=RETRY_TIMES, base_delay=1.0, jitter=0.5)(fn)
    result = runner(*args, **kwargs)
    if use_cache:
        _CACHE[key] = result
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetch.py -v`
Expected: PASS

---

## Task 6: 单位换算

**Files:**
- Create: `backend/core/units.py`
- Test: `tests/test_units.py`

**Interfaces:**
- Produces: `to_yi(value) -> float | None`、`pct(value) -> float | None`。

- [ ] **Step 1: 写失败测试 `tests/test_units.py`**

```python
from backend.core.units import to_yi, pct


def test_to_yi():
    assert to_yi(1_0000_0000) == 1.0
    assert to_yi(5.2e11) == 5200.0
    assert to_yi(None) is None
    assert to_yi("abc") is None


def test_pct():
    assert pct("1.234") == 1.23
    assert pct(None) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_units.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/core/units.py`**

```python
def to_yi(value):
    try:
        return round(float(value) / 1e8, 2)
    except (TypeError, ValueError):
        return None


def pct(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_units.py -v`
Expected: PASS

---

## Task 7: 快照服务（错误隔离 + 量能增减 + 原子写）

**Files:**
- Create: `backend/services/snapshot.py`
- Test: `tests/test_snapshot.py`

**Interfaces:**
- Produces:
  - `build_snapshot(fetchers: dict, data_dir: Path, date: str | None = None) -> dict`
  - `load_snapshot(data_dir: Path, date: str) -> dict | None`
  - `get_or_create(fetchers: dict, data_dir: Path, date: str | None = None, force: bool = False) -> dict`
  - 内部 `_prev_date(data_dir, date) -> str | None`、`_attach_turnover_delta(snapshot, data_dir, date) -> None`

- [ ] **Step 1: 写失败测试 `tests/test_snapshot.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_snapshot.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/services/snapshot.py`**

```python
import datetime as dt
import json
import os
from pathlib import Path

from backend.core.logging import get_logger

logger = get_logger("snapshot")


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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_snapshot.py -v`
Expected: PASS

---

## Task 8: A股指数 fetcher（含涨跌分布）

**Files:**
- Create: `backend/fetchers/a_index.py`
- Test: `tests/test_fetcher_a_index.py`

**Interfaces:**
- Produces: `fetch_a_index() -> dict`，键：`as_of, prev_date, indices[], history{}, turnover{}, breadth{...distribution}`。
- 依赖 akshare：`stock_zh_index_spot_sina`、`stock_zh_index_daily`、`stock_market_activity_legu`、`stock_sse_deal_daily`、`stock_zh_a_spot`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_a_index.py`**

```python
import pandas as pd
import pytest

import backend.fetchers.a_index as mod
from backend.fetchers.a_index import fetch_a_index


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_a_index(monkeypatch):
    spot = pd.DataFrame([
        {"代码": "sh000001", "名称": "上证指数", "最新价": 3880.5, "涨跌额": 12.3, "涨跌幅": 0.31, "成交量": 4.1e10, "成交额": 5.2e11},
        {"代码": "sz399001", "名称": "深证成指", "最新价": 12000.0, "涨跌额": -30.0, "涨跌幅": -0.25, "成交量": 5e10, "成交额": 6e11},
    ])
    hist = pd.DataFrame([
        {"date": "2026-09-30", "open": 3800.0, "high": 3820.0, "low": 3790.0, "close": 3810.0, "volume": 3.9e10},
        {"date": "2026-10-03", "open": 3870.0, "high": 3890.0, "low": 3860.0, "close": 3880.5, "volume": 4.1e10},
    ])
    legu = pd.DataFrame([
        {"item": "上涨", "value": 3000}, {"item": "下跌", "value": 1800},
        {"item": "平盘", "value": 200}, {"item": "涨停", "value": 60}, {"item": "跌停", "value": 10},
        {"item": "活跃度", "value": "正常"},
    ])
    allspot = pd.DataFrame([{"代码": f"sz{100000+i}", "名称": "x", "涨跌幅": v}
                            for i, v in enumerate([-8, -6, -4, -1, 1, 4, 6, 9])])
    monkeypatch.setattr(mod.ak, "stock_zh_index_spot_sina", lambda: spot)
    monkeypatch.setattr(mod.ak, "stock_zh_index_daily", lambda symbol: hist)
    monkeypatch.setattr(mod.ak, "stock_market_activity_legu", lambda: legu)
    monkeypatch.setattr(mod.ak, "stock_sse_deal_daily", lambda: pd.DataFrame([{"单日情况": "股票", "主板A": 1}]))
    monkeypatch.setattr(mod.ak, "stock_zh_a_spot", lambda: allspot)

    out = fetch_a_index()
    assert out["breadth"]["up"] == 3000
    buckets = {d["label"]: d["count"] for d in out["breadth"]["distribution"]}
    assert buckets["≤-7%"] == 1 and buckets["≥7%"] == 1
    assert out["history"]["sh000001"][-1]["close"] == 3880.5
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetcher_a_index.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/fetchers/a_index.py`**

```python
import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct

TARGET_INDICES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000300": "沪深300",
    "sh000852": "中证1000",
    "sh000688": "科创50",
}
HISTORY_DAYS = 60
DIST_BUCKETS = [
    ("≤-7%", lambda v: v <= -7), ("-7~-5%", lambda v: -7 < v <= -5),
    ("-5~-3%", lambda v: -5 < v <= -3), ("-3~0%", lambda v: -3 < v < 0),
    ("0~3%", lambda v: 0 <= v < 3), ("3~5%", lambda v: 3 <= v < 5),
    ("5~7%", lambda v: 5 <= v < 7), ("≥7%", lambda v: v >= 7),
]


def _distribution(spot_df) -> list:
    values = []
    for v in spot_df["涨跌幅"]:
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    return [{"label": label, "count": sum(1 for v in values if fn(v))} for label, fn in DIST_BUCKETS]


def fetch_a_index() -> dict:
    spot = fetch(ak.stock_zh_index_spot_sina, source="sina")
    spot_by_code = {str(r["代码"]): r for _, r in spot.iterrows()}

    indices, history = [], {}
    for code, name in TARGET_INDICES.items():
        row = spot_by_code.get(code)
        if row is None:
            continue
        indices.append({
            "code": code, "name": name,
            "price": float(row["最新价"]),
            "change": pct(row.get("涨跌额")),
            "change_pct": pct(row.get("涨跌幅")),
            "amount": float(row["成交额"]) if row.get("成交额") is not None else None,
            "volume": float(row["成交量"]) if row.get("成交量") is not None else None,
        })
        hist = fetch(ak.stock_zh_index_daily, symbol=code, source="sina").tail(HISTORY_DAYS)
        history[code] = [
            {"date": str(r["date"]), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]), "volume": float(r["volume"])}
            for _, r in hist.iterrows()
        ]

    legu = fetch(ak.stock_market_activity_legu, source="legu")
    bmap = {str(r["item"]): r["value"] for _, r in legu.iterrows()}
    allspot = fetch(ak.stock_zh_a_spot, source="sina")
    breadth = {
        "up": int(bmap.get("上涨", 0)), "down": int(bmap.get("下跌", 0)),
        "flat": int(bmap.get("平盘", 0)), "limit_up": int(bmap.get("涨停", 0)),
        "limit_down": int(bmap.get("跌停", 0)), "activity": str(bmap.get("活跃度", "")),
        "distribution": _distribution(allspot),
    }

    notes = []
    sh_amount = None
    try:
        sse = fetch(ak.stock_sse_deal_daily, source="sse")
        row = sse[sse["单日情况"].astype(str).str.contains("股票")].head(1)
        if not row.empty:
            sh_amount = float(row.iloc[0].get("主板A", 0) or 0)
    except Exception:
        notes.append("沪市成交额获取失败")
    sz_amount = None
    for i in indices:
        if i["code"] == "sz399001" and i["amount"] is not None:
            sz_amount = round(i["amount"] / 1e8, 2)
    if sz_amount is None:
        notes.append("深市成交额获取失败")
    total = None
    if sh_amount is not None or sz_amount is not None:
        total = round((sh_amount or 0) + (sz_amount or 0), 2)

    turnover = {"sh": sh_amount, "sz": sz_amount, "total": total, "unit": "亿元", "notes": notes}

    prev_date = None
    if history.get("sh000001"):
        dates = [h["date"] for h in history["sh000001"]]
        prev_date = dates[-2] if len(dates) >= 2 else dates[-1]

    return {
        "as_of": history.get("sh000001", [{}])[-1].get("date") if history.get("sh000001") else None,
        "prev_date": prev_date, "indices": indices, "history": history,
        "turnover": turnover, "breadth": breadth,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetcher_a_index.py -v`
Expected: PASS

---

## Task 9: 外围风向 fetcher

**Files:**
- Create: `backend/fetchers/overseas.py`
- Test: `tests/test_fetcher_overseas.py`

**Interfaces:**
- Produces: `fetch_overseas() -> dict`，键：`as_of, us_indices[], futures[], hk_indices[], sox{}, usd_cny{}`。
- 依赖 akshare：`index_us_stock_sina`、`futures_global_spot_em`、`stock_hk_index_spot_sina`、`macro_global_sox_index`、`currency_boc_sina`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_overseas.py`**

```python
import datetime as dt
import pandas as pd
import pytest

import backend.fetchers.overseas as mod
from backend.fetchers.overseas import fetch_overseas


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_overseas(monkeypatch):
    def us_index(symbol):
        return pd.DataFrame([
            {"date": "2026-10-01", "open": 1, "high": 1, "low": 1, "close": 100.0, "volume": 1, "amount": 1},
            {"date": "2026-10-02", "open": 1, "high": 1, "low": 1, "close": 101.0, "volume": 1, "amount": 1},
        ])
    futures = pd.DataFrame([
        {"代码": "CN00Y", "名称": "A50期指当月连续", "最新价": 13830.0, "涨跌额": 20.0, "涨跌幅": 0.14},
        {"代码": "XX", "名称": "不相关", "最新价": 1.0, "涨跌额": 0.0, "涨跌幅": 0.0},
    ])
    hk = pd.DataFrame([
        {"代码": "HSI", "名称": "恒生指数", "最新价": 23972.29, "涨跌额": -641.0, "涨跌幅": -2.60},
        {"代码": "HSTECH", "名称": "恒生科技指数", "最新价": 4157.94, "涨跌额": -96.0, "涨跌幅": -2.26},
        {"代码": "OTHER", "名称": "无关", "最新价": 1.0, "涨跌额": 0.0, "涨跌幅": 0.0},
    ])
    sox = pd.DataFrame([{"日期": "2026-10-02", "最新值": 5200.0, "涨跌幅": 0.8}])
    fx = pd.DataFrame([{"日期": "2026-10-03", "央行中间价": 7.1050}])

    monkeypatch.setattr(mod.ak, "index_us_stock_sina", us_index)
    monkeypatch.setattr(mod.ak, "futures_global_spot_em", lambda: futures)
    monkeypatch.setattr(mod.ak, "stock_hk_index_spot_sina", lambda: hk)
    monkeypatch.setattr(mod.ak, "macro_global_sox_index", lambda: sox)
    monkeypatch.setattr(mod.ak, "currency_boc_sina", lambda **k: fx)

    out = fetch_overseas()
    assert next(i for i in out["us_indices"] if i["code"] == ".DJI")["change_pct"] == 1.0
    assert {f["name"] for f in out["futures"]} == {"A50期指当月连续"}
    assert {h["code"] for h in out["hk_indices"]} == {"HSI", "HSTECH"}
    assert out["sox"]["value"] == 5200.0
    assert out["usd_cny"]["mid"] == 7.1050
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetcher_overseas.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/fetchers/overseas.py`**

```python
import datetime as dt

import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct

US_INDICES = {".DJI": "道琼斯", ".IXIC": "纳斯达克", ".INX": "标普500"}
FUTURE_KEYS = ("A50期指当月连续", "小型标普当月连续")
HK_CODES = {"HSI": "恒生指数", "HSTECH": "恒生科技指数", "HSCEI": "恒生国企指数", "HSCCI": "恒生中资企业指数"}


def _us_indices():
    rows, as_of = [], None
    for code, name in US_INDICES.items():
        df = fetch(ak.index_us_stock_sina, symbol=code, source="sina")
        if df.empty:
            continue
        last = df.iloc[-1]
        prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(last["close"])
        close = float(last["close"])
        as_of = str(last["date"])
        rows.append({
            "code": code, "name": name, "close": close,
            "change": pct(close - prev_close),
            "change_pct": pct((close - prev_close) / prev_close * 100) if prev_close else None,
        })
    return rows, as_of


def fetch_overseas() -> dict:
    us_indices, as_of = _us_indices()

    fdf = fetch(ak.futures_global_spot_em, source="em_push2ex")
    futures = []
    for _, row in fdf.iterrows():
        if any(k in str(row["名称"]) for k in FUTURE_KEYS):
            futures.append({
                "code": str(row["代码"]), "name": str(row["名称"]),
                "price": float(row["最新价"]) if row["最新价"] == row["最新价"] else None,
                "change_pct": pct(row.get("涨跌幅")),
            })

    hkdf = fetch(ak.stock_hk_index_spot_sina, source="sina")
    hk_indices = []
    for _, row in hkdf.iterrows():
        code = str(row["代码"])
        if code in HK_CODES:
            hk_indices.append({
                "code": code, "name": HK_CODES.get(code, str(row["名称"])),
                "price": float(row["最新价"]), "change_pct": pct(row.get("涨跌幅")),
            })

    sox = {}
    try:
        sdf = fetch(ak.macro_global_sox_index, source="legu")
        if not sdf.empty:
            last = sdf.iloc[-1]
            sox = {"date": str(last["日期"]), "value": float(last["最新值"]), "change_pct": pct(last.get("涨跌幅"))}
    except Exception:
        sox = {}

    usd_cny = {}
    try:
        end = dt.date.today()
        start = end - dt.timedelta(days=7)
        fdf2 = fetch(ak.currency_boc_sina, symbol="美元",
                     start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), source="sina")
        if not fdf2.empty:
            last = fdf2.iloc[-1]
            usd_cny = {"date": str(last["日期"]), "mid": float(last["央行中间价"]),
                       "note": "中行牌价(代理，非离岸CNH)"}
    except Exception:
        usd_cny = {}

    return {"as_of": as_of, "us_indices": us_indices, "futures": futures,
            "hk_indices": hk_indices, "sox": sox, "usd_cny": usd_cny}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetcher_overseas.py -v`
Expected: PASS

---

## Task 10: 情绪博弈 fetcher

**Files:**
- Create: `backend/fetchers/sentiment.py`
- Test: `tests/test_fetcher_sentiment.py`

**Interfaces:**
- Produces: `fetch_sentiment() -> dict`，键：`date, limit_up, limit_down, zbgc, zbgc_rate, max_boards, boards_distribution[], promotion_rate, prev_limit_up_count, top_boards[]`。
- 依赖 akshare：`stock_zh_index_daily`、`stock_zt_pool_em`、`stock_zt_pool_dtgc_em`、`stock_zt_pool_zbgc_em`、`stock_zt_pool_previous_em`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_sentiment.py`**

```python
import pandas as pd
import pytest

import backend.fetchers.sentiment as mod
from backend.fetchers.sentiment import fetch_sentiment


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_sentiment(monkeypatch):
    idx = pd.DataFrame([{"date": "2026-09-30", "open": 1, "high": 1, "low": 1, "close": 3800.0, "volume": 1}])
    zt = pd.DataFrame([
        {"代码": "002058", "名称": "紫竹高科", "连板数": 2, "所属行业": "电池"},
        {"代码": "002242", "名称": "九阳股份", "连板数": 3, "所属行业": "小家电"},
        {"代码": "600000", "名称": "浦发银行", "连板数": 1, "所属行业": "银行"},
    ])
    dt_ = pd.DataFrame([{"代码": "600156", "名称": "华升股份"}])
    zb = pd.DataFrame([{"代码": "300001", "名称": "x"}])
    prev = pd.DataFrame([
        {"代码": "000002", "名称": "万科A", "涨跌幅": 9.97},
        {"代码": "000003", "名称": "B", "涨跌幅": 2.0},
    ])

    monkeypatch.setattr(mod.ak, "stock_zh_index_daily", lambda symbol: idx)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_em", lambda date: zt)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_dtgc_em", lambda date: dt_)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_zbgc_em", lambda date: zb)
    monkeypatch.setattr(mod.ak, "stock_zt_pool_previous_em", lambda date: prev)

    out = fetch_sentiment()
    assert out["date"] == "20260930"
    assert out["limit_up"] == 3 and out["limit_down"] == 1
    assert out["zbgc"] == 1
    assert abs(out["zbgc_rate"] - 0.25) < 1e-6
    assert out["max_boards"] == 3
    assert out["top_boards"][0]["name"] == "九阳股份"
    assert out["promotion_rate"] == 0.5
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetcher_sentiment.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/fetchers/sentiment.py`**

```python
from collections import Counter

import akshare as ak

from backend.core.fetch import fetch


def _latest_date() -> str:
    df = fetch(ak.stock_zh_index_daily, symbol="sh000001", source="sina")
    return str(df.iloc[-1]["date"]).replace("-", "")


def fetch_sentiment() -> dict:
    date = _latest_date()

    zt = fetch(ak.stock_zt_pool_em, date=date, source="em_push2ex")
    dt_pool = fetch(ak.stock_zt_pool_dtgc_em, date=date, source="em_push2ex")
    zb = fetch(ak.stock_zt_pool_zbgc_em, date=date, source="em_push2ex")

    limit_up = int(len(zt))
    limit_down = int(len(dt_pool))
    zbgc = int(len(zb))
    denom = limit_up + zbgc
    zbgc_rate = round(zbgc / denom, 4) if denom else None

    boards = []
    distribution = []
    if "连板数" in zt.columns and limit_up:
        boards = [int(v) for v in zt["连板数"].tolist()]
        distribution = [{"boards": b, "count": c} for b, c in sorted(Counter(boards).items())]
    max_boards = max(boards) if boards else None

    top_boards = []
    if limit_up:
        sorted_zt = zt.sort_values("连板数", ascending=False).head(5)
        top_boards = [{"name": str(r["名称"]), "boards": int(r["连板数"]), "industry": str(r.get("所属行业", ""))}
                      for _, r in sorted_zt.iterrows()]

    prev = fetch(ak.stock_zt_pool_previous_em, date=date, source="em_push2ex")
    prev_count = int(len(prev))
    promotion_rate = None
    if prev_count and "涨跌幅" in prev.columns:
        promoted = sum(1 for v in prev["涨跌幅"] if float(v) >= 9.8)
        promotion_rate = round(promoted / prev_count, 4)

    return {
        "date": date, "limit_up": limit_up, "limit_down": limit_down,
        "zbgc": zbgc, "zbgc_rate": zbgc_rate, "max_boards": max_boards,
        "boards_distribution": distribution, "promotion_rate": promotion_rate,
        "prev_limit_up_count": prev_count, "top_boards": top_boards,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetcher_sentiment.py -v`
Expected: PASS

---

## Task 11: 北向资金 fetcher

**Files:**
- Create: `backend/fetchers/northbound.py`
- Test: `tests/test_fetcher_northbound.py`

**Interfaces:**
- Produces: `fetch_northbound() -> dict`，键：`as_of, total_net_buy, summary[], history[]`。
- 依赖 akshare：`stock_hsgt_fund_flow_summary_em`、`stock_hsgt_hist_em`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_northbound.py`**

```python
import pandas as pd
import pytest

import backend.fetchers.northbound as mod
from backend.fetchers.northbound import fetch_northbound


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_northbound(monkeypatch):
    summary = pd.DataFrame([
        {"交易日": "2026-10-03", "资金方向": "北向", "板块": "沪股通", "成交净买额": 30.1, "上涨数": 941, "持平数": 41, "下跌数": 662},
        {"交易日": "2026-10-03", "资金方向": "南向", "板块": "港股通(沪)", "成交净买额": 50.0, "上涨数": 1, "持平数": 1, "下跌数": 1},
        {"交易日": "2026-10-03", "资金方向": "北向", "板块": "深股通", "成交净买额": 20.8, "上涨数": 880, "持平数": 30, "下跌数": 700},
    ])
    hist = pd.DataFrame([{"日期": "2026-09-30", "当日成交净买额": 5.0},
                         {"日期": "2026-10-01", "当日成交净买额": 12.3}])
    monkeypatch.setattr(mod.ak, "stock_hsgt_fund_flow_summary_em", lambda: summary)
    monkeypatch.setattr(mod.ak, "stock_hsgt_hist_em", lambda symbol: hist)

    out = fetch_northbound()
    assert {s["board"] for s in out["summary"]} == {"沪股通", "深股通"}
    assert abs(out["total_net_buy"] - 50.9) < 1e-6
    assert out["history"][-1]["net_buy"] == 12.3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetcher_northbound.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/fetchers/northbound.py`**

```python
import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct

HISTORY_DAYS = 30


def fetch_northbound() -> dict:
    summary_df = fetch(ak.stock_hsgt_fund_flow_summary_em, source="em_datacenter")
    north = summary_df[summary_df["资金方向"].astype(str) == "北向"]
    summary, total, as_of = [], 0.0, None
    for _, row in north.iterrows():
        net = float(row["成交净买额"]) if row["成交净买额"] == row["成交净买额"] else 0.0
        total += net
        as_of = str(row["交易日"])
        summary.append({"board": str(row["板块"]), "net_buy": pct(net),
                        "up": int(row["上涨数"]), "flat": int(row["持平数"]), "down": int(row["下跌数"])})

    hist_df = fetch(ak.stock_hsgt_hist_em, symbol="北向资金", source="em_datacenter").tail(HISTORY_DAYS)
    history = [{"date": str(r["日期"]), "net_buy": pct(r["当日成交净买额"])} for _, r in hist_df.iterrows()]

    return {"as_of": as_of, "total_net_buy": pct(total), "summary": summary, "history": history}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetcher_northbound.py -v`
Expected: PASS

---

## Task 12: 申万一级行业 fetcher

**Files:**
- Create: `backend/fetchers/sw_industry.py`
- Test: `tests/test_fetcher_sw_industry.py`

**Interfaces:**
- Produces: `fetch_sw_industry() -> dict`，键：`as_of, industries[]`。
- 依赖 akshare：`index_realtime_sw`、`index_component_sw`、`stock_zh_a_spot`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_sw_industry.py`**

```python
import pandas as pd
import pytest

import backend.fetchers.sw_industry as mod
from backend.fetchers.sw_industry import fetch_sw_industry


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_sw_industry(monkeypatch):
    realtime = pd.DataFrame([
        {"指数代码": "801010", "指数名称": "农林牧渔", "最新价": 2600.0, "涨跌幅": 1.2, "成交额": 1.2e10},
        {"指数代码": "801030", "指数名称": "基础化工", "最新价": 3200.0, "涨跌幅": -0.5, "成交额": 2.0e10},
    ])
    def cons(symbol):
        return pd.DataFrame({"证券代码": ["000505", "000592", "999999"]})
    spot = pd.DataFrame([
        {"代码": "sz000505", "涨跌幅": 2.0}, {"代码": "sz000592", "涨跌幅": -1.0},
        {"代码": "sh999999", "涨跌幅": 0.0},
    ])
    monkeypatch.setattr(mod.ak, "index_realtime_sw", lambda symbol: realtime)
    monkeypatch.setattr(mod.ak, "index_component_sw", cons)
    monkeypatch.setattr(mod.ak, "stock_zh_a_spot", lambda: spot)

    out = fetch_sw_industry()
    ind = next(i for i in out["industries"] if i["code"] == "801010")
    assert (ind["up_count"], ind["down_count"], ind["flat_count"]) == (1, 1, 1)
    assert out["industries"][0]["code"] == "801010"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetcher_sw_industry.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/fetchers/sw_industry.py`**

```python
import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct


def _normalize_code(code: str) -> str:
    code = str(code).strip()
    for prefix in ("sh", "sz", "bj"):
        if code.startswith(prefix):
            return code[len(prefix):]
    return code


def fetch_sw_industry() -> dict:
    realtime = fetch(ak.index_realtime_sw, symbol="一级行业", source="sw")
    spot = fetch(ak.stock_zh_a_spot, source="sina")
    pct_by_code = {_normalize_code(r["代码"]): r["涨跌幅"] for _, r in spot.iterrows()}

    industries = []
    for _, row in realtime.iterrows():
        code = str(row["指数代码"])
        cons = fetch(ak.index_component_sw, symbol=code, source="sw")
        up = down = flat = 0
        for _, c in cons.iterrows():
            chg = pct_by_code.get(_normalize_code(c["证券代码"]))
            if chg is None:
                continue
            chg = float(chg)
            if chg > 0:
                up += 1
            elif chg < 0:
                down += 1
            else:
                flat += 1
        industries.append({
            "code": code, "name": str(row["指数名称"]),
            "price": float(row["最新价"]), "change_pct": pct(row.get("涨跌幅")),
            "amount": float(row["成交额"]) if row.get("成交额") is not None else None,
            "up_count": up, "down_count": down, "flat_count": flat,
        })
    industries.sort(key=lambda x: (x["change_pct"] is None, -(x["change_pct"] or 0)))
    return {"as_of": None, "industries": industries}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetcher_sw_industry.py -v`
Expected: PASS

---

## Task 13: 概念 + 同花顺行业资金流 fetcher

**Files:**
- Create: `backend/fetchers/sector_flow.py`
- Test: `tests/test_fetcher_sector_flow.py`

**Interfaces:**
- Produces: `fetch_sector_flow() -> dict`，键：`as_of, concepts[], industries[]`。
- 依赖 akshare：`stock_fund_flow_concept`、`stock_board_industry_summary_ths`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_sector_flow.py`**

```python
import pandas as pd
import pytest

import backend.fetchers.sector_flow as mod
from backend.fetchers.sector_flow import fetch_sector_flow


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_sector_flow(monkeypatch):
    concepts = pd.DataFrame([
        {"行业": "重组蛋白", "行业指数": 851.77, "行业-涨跌幅": 3.78, "流入资金": 95.52, "流出资金": 75.58,
         "净额": 19.94, "公司家数": 128, "领涨股": "泰诺麦博", "领涨股-涨跌幅": 19.99},
        {"行业": "银行", "行业指数": 3000.0, "行业-涨跌幅": -0.2, "流入资金": 10.0, "流出资金": 20.0,
         "净额": -10.0, "公司家数": 42, "领涨股": "X", "领涨股-涨跌幅": 1.0},
    ])
    industries = pd.DataFrame([
        {"板块": "生物制品", "涨跌幅": 4.63, "总成交额": 236.62, "净流入": 14.36, "上涨家数": 53,
         "下跌家数": 2, "领涨股": "康希诺", "领涨股-涨跌幅": 20.0},
    ])
    monkeypatch.setattr(mod.ak, "stock_fund_flow_concept", lambda symbol: concepts)
    monkeypatch.setattr(mod.ak, "stock_board_industry_summary_ths", lambda: industries)

    out = fetch_sector_flow()
    assert out["concepts"][0]["name"] == "重组蛋白"       # 净额降序
    assert out["concepts"][0]["net_inflow"] == 19.94
    assert out["industries"][0]["name"] == "生物制品"
    assert out["industries"][0]["up_count"] == 53
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetcher_sector_flow.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/fetchers/sector_flow.py`**

```python
import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import pct


def fetch_sector_flow() -> dict:
    cdf = fetch(ak.stock_fund_flow_concept, symbol="即时", source="ths")
    concepts = []
    for _, row in cdf.iterrows():
        concepts.append({
            "name": str(row["行业"]),
            "index": float(row["行业指数"]) if row.get("行业指数") == row.get("行业指数") else None,
            "change_pct": pct(row.get("行业-涨跌幅")),
            "net_inflow": pct(row.get("净额")),
            "inflow": pct(row.get("流入资金")),
            "outflow": pct(row.get("流出资金")),
            "company_count": int(row["公司家数"]) if row.get("公司家数") == row.get("公司家数") else None,
            "leader": str(row.get("领涨股", "")),
            "leader_change_pct": pct(row.get("领涨股-涨跌幅")),
        })
    concepts.sort(key=lambda x: (x["net_inflow"] is None, -(x["net_inflow"] or 0)))

    idf = fetch(ak.stock_board_industry_summary_ths, source="ths")
    industries = []
    for _, row in idf.iterrows():
        industries.append({
            "name": str(row["板块"]),
            "change_pct": pct(row.get("涨跌幅")),
            "amount": pct(row.get("总成交额")),
            "net_inflow": pct(row.get("净流入")),
            "up_count": int(row["上涨家数"]) if row.get("上涨家数") == row.get("上涨家数") else None,
            "down_count": int(row["下跌家数"]) if row.get("下跌家数") == row.get("下跌家数") else None,
            "leader": str(row.get("领涨股", "")),
            "leader_change_pct": pct(row.get("领涨股-涨跌幅")),
        })
    industries.sort(key=lambda x: (x["change_pct"] is None, -(x["change_pct"] or 0)))

    return {"as_of": None, "concepts": concepts, "industries": industries}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetcher_sector_flow.py -v`
Expected: PASS

---

## Task 14: 主力资金/两融 fetcher（best-effort）

**Files:**
- Create: `backend/fetchers/capital.py`
- Test: `tests/test_fetcher_capital.py`

**Interfaces:**
- Produces: `fetch_capital() -> dict`，键：`as_of, main_net_inflow, margin_total, notes[]`。
- 依赖 akshare：`stock_market_fund_flow`、`stock_margin_sse`、`stock_margin_szse`。

- [ ] **Step 1: 写失败测试 `tests/test_fetcher_capital.py`**

```python
import pandas as pd
import pytest

import backend.fetchers.capital as mod
from backend.fetchers.capital import fetch_capital


@pytest.fixture(autouse=True)
def _no_rate(monkeypatch):
    import backend.core.fetch as fetchmod
    from backend.core.ratelimit import RateLimiter
    fetchmod.reset_cache()
    fetchmod.LIMITER = RateLimiter(min_interval=0.0)


def test_fetch_capital_partial(monkeypatch):
    mf = pd.DataFrame([{"日期": "2026-09-30", "主力净流入-净额": 3.5e10}])
    sse = pd.DataFrame([{"信用交易日期": "20260930", "融资融券余额": 1.9e12}])

    def szse():
        raise RuntimeError("szse down")

    monkeypatch.setattr(mod.ak, "stock_market_fund_flow", lambda: mf)
    monkeypatch.setattr(mod.ak, "stock_margin_sse", lambda: sse)
    monkeypatch.setattr(mod.ak, "stock_margin_szse", szse)

    out = fetch_capital()
    assert out["main_net_inflow"] == 350.0      # 3.5e10 元 → 350 亿
    assert out["margin_total"] is not None
    assert any("深" in n for n in out["notes"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_fetcher_capital.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/fetchers/capital.py`**

```python
import akshare as ak

from backend.core.fetch import fetch
from backend.core.units import to_yi


def fetch_capital() -> dict:
    notes = []
    as_of = None
    main_net_inflow = None
    try:
        mf = fetch(ak.stock_market_fund_flow, source="em_datacenter")
        if not mf.empty:
            last = mf.iloc[-1]
            as_of = str(last.get("日期"))
            main_net_inflow = to_yi(last.get("主力净流入-净额"))
    except Exception as exc:
        notes.append(f"主力资金获取失败: {exc}")

    margin_total = None
    try:
        sse = fetch(ak.stock_margin_sse, source="sse")
        if not sse.empty:
            margin_total = to_yi(sse.iloc[-1].get("融资融券余额"))
    except Exception as exc:
        notes.append(f"沪市两融获取失败: {exc}")
    try:
        fetch(ak.stock_margin_szse, source="szse")
    except Exception as exc:
        notes.append(f"深市两融获取失败(已跳过): {exc}")

    return {"as_of": as_of, "main_net_inflow": main_net_inflow,
            "margin_total": margin_total, "notes": notes}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_fetcher_capital.py -v`
Expected: PASS

---

## Task 15: FastAPI 应用与路由

**Files:**
- Create: `backend/app.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `force_ipv4`、`setup_logging`、`get_or_create`、7 个 fetcher。
- Produces: `build_app(data_dir: Path | None = None, fetchers: dict | None = None) -> FastAPI`；模块级 `app`。

- [ ] **Step 1: 写失败测试 `tests/test_api.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_api.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 `backend/app.py`**

```python
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.core.logging import get_logger, setup_logging
from backend.core.net import force_ipv4
from backend.fetchers.a_index import fetch_a_index
from backend.fetchers.capital import fetch_capital
from backend.fetchers.northbound import fetch_northbound
from backend.fetchers.overseas import fetch_overseas
from backend.fetchers.sector_flow import fetch_sector_flow
from backend.fetchers.sentiment import fetch_sentiment
from backend.fetchers.sw_industry import fetch_sw_industry
from backend.services.snapshot import get_or_create

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backend" / "data" / "snapshots"
FRONTEND_DIR = ROOT / "frontend"

DEFAULT_FETCHERS = {
    "overseas": fetch_overseas,
    "a_index": fetch_a_index,
    "sentiment": fetch_sentiment,
    "northbound": fetch_northbound,
    "sw_industry": fetch_sw_industry,
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

    @app.get("/api/snapshot")
    def snapshot():
        snap = get_or_create(_fetchers, _data_dir, force=False)
        if all(v == "error" for v in snap["sources"].values()):
            raise HTTPException(status_code=502, detail="全部数据源获取失败")
        return snap

    @app.post("/api/refresh")
    def refresh():
        snap = get_or_create(_fetchers, _data_dir, force=True)
        if all(v == "error" for v in snap["sources"].values()):
            raise HTTPException(status_code=502, detail="全部数据源获取失败")
        return snap

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    return app


app = build_app()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python3 -m pytest tests/test_api.py -v`
Expected: PASS

---

## Task 16: 前端骨架与样式（深色 3 屏）

**Files:**
- Create: `frontend/vendor/echarts.min.js`
- Create: `frontend/index.html`
- Create: `frontend/style.css`
- Test: `tests/test_frontend_assets.py`

**Interfaces:**
- Consumes: `/api/snapshot` schema（spec §6）、`/api/refresh`。
- Produces: 页面骨架（屏一/二/三）+ 设计令牌样式。

- [ ] **Step 1: 下载本地 ECharts（备用源）**

```bash
mkdir -p frontend/vendor
curl -sL -o frontend/vendor/echarts.min.js "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js" \
  || curl -sL -o frontend/vendor/echarts.min.js "https://registry.npmmirror.com/echarts/5.5.1/files/dist/echarts.min.js"
ls -la frontend/vendor/echarts.min.js && head -c 60 frontend/vendor/echarts.min.js
```

- [ ] **Step 2: 写失败测试 `tests/test_frontend_assets.py`**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_files_exist():
    for name in ("index.html", "style.css", "app.js", "vendor/echarts.min.js"):
        assert (ROOT / "frontend" / name).exists(), name


def test_index_references_assets():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "/static/app.js" in html and "echarts.min.js" in html


def test_style_has_tokens():
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    for token in ("#0e1117", "#ff4d4f", "#22c55e", "#f5c451"):
        assert token in css
```

- [ ] **Step 3: 写 `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>股市脉搏看板</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <header class="topbar">
    <div class="brand">股市脉搏</div>
    <div class="meta" id="meta">加载中…</div>
    <div class="srcstatus" id="srcstatus"></div>
    <button id="refresh" class="btn">重新抓取</button>
  </header>

  <main>
    <section class="screen">
      <h2 class="screen-title">屏一 · 市场全局与情绪</h2>
      <div class="grid grid-2">
        <div class="panel"><h3>外围风向</h3><div class="cards" id="overseas-cards"></div></div>
        <div class="panel"><h3>A股大盘与量能</h3><div class="cards" id="a-cards"></div>
          <div class="stats" id="a-stats"></div></div>
      </div>
      <div class="grid grid-2">
        <div class="panel"><h3>情绪博弈</h3><div class="cards" id="sentiment-cards"></div>
          <div class="mini" id="sentiment-top"></div></div>
        <div class="panel"><h3>大盘近60日走势</h3><div class="chart" id="chart-index"></div></div>
      </div>
      <div class="panel"><h3>涨跌分布梯度</h3><div class="chart" id="chart-dist"></div></div>
    </section>

    <section class="screen">
      <h2 class="screen-title">屏二 · 资金主线与板块轮动</h2>
      <div class="grid grid-2">
        <div class="panel">
          <h3>概念资金流（同花顺）
            <button class="mini-btn" data-sort="net" onclick="setFlowSort('net')">按净额</button>
            <button class="mini-btn" data-sort="chg" onclick="setFlowSort('chg')">按涨幅</button>
          </h3>
          <div class="table-wrap"><table id="concept-table"></table></div>
        </div>
        <div class="panel"><h3>申万一级热力图（块=成交额，色=涨跌幅）</h3>
          <div class="chart tall" id="chart-treemap"></div></div>
      </div>
      <div class="panel"><h3>同花顺行业(90)</h3>
        <div class="table-wrap"><table id="ths-table"></table></div></div>
    </section>

    <section class="screen">
      <h2 class="screen-title">屏三 · 长线资金</h2>
      <div class="grid grid-2">
        <div class="panel"><h3>北向资金</h3><div class="cards" id="north-cards"></div></div>
        <div class="panel"><h3>北向净买额（近30日）</h3><div class="chart" id="chart-north"></div></div>
      </div>
      <div class="grid grid-2">
        <div class="panel"><h3>主力资金</h3><div class="cards" id="capital-cards"></div></div>
        <div class="panel"><h3>融资融券</h3><div class="cards" id="margin-cards"></div></div>
      </div>
    </section>
  </main>

  <div class="overlay" id="overlay">正在抓取数据，请稍候…</div>
  <script src="/static/vendor/echarts.min.js"></script>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: 写 `frontend/style.css`**

```css
:root {
  --bg:#0e1117; --panel:#161b26; --panel-2:#1e2430; --border:#2a3141;
  --text:#e6e9ef; --text-muted:#8b93a7; --up:#ff4d4f; --down:#22c55e;
  --flat:#8b93a7; --accent:#3b82f6; --gold:#f5c451;
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; }
.topbar { display:flex; align-items:center; gap:16px; padding:12px 20px;
  background:var(--panel); border-bottom:1px solid var(--border);
  position:sticky; top:0; z-index:10; }
.brand { font-size:18px; font-weight:700; color:var(--gold); letter-spacing:2px; }
.meta, .srcstatus { color:var(--text-muted); font-size:13px; }
.btn { margin-left:auto; background:var(--accent); color:#fff; border:none;
  padding:6px 16px; border-radius:6px; cursor:pointer; font-size:13px; }
.btn:disabled { opacity:.5; cursor:not-allowed; }
main { padding:16px 20px 60px; display:flex; flex-direction:column; gap:20px; }
.screen-title { font-size:14px; color:var(--accent); margin:0 0 10px; letter-spacing:1px; }
.grid { display:grid; gap:14px; margin-bottom:14px; }
.grid-2 { grid-template-columns:repeat(2, minmax(0,1fr)); }
@media (max-width:1100px){ .grid-2{ grid-template-columns:1fr; } }
.panel { background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:14px 16px; }
.panel h3 { margin:0 0 12px; font-size:14px; font-weight:600; color:var(--gold);
  display:flex; align-items:center; gap:8px; }
.cards { display:flex; flex-wrap:wrap; gap:10px; }
.card { background:var(--panel-2); border:1px solid var(--border); border-radius:8px;
  padding:10px 14px; min-width:140px; }
.card .name { color:var(--text-muted); font-size:12px; margin-bottom:4px; }
.card .val { font-size:19px; font-weight:700; font-variant-numeric:tabular-nums; }
.card .sub { font-size:12px; margin-top:2px; font-variant-numeric:tabular-nums; }
.stats { margin-top:12px; color:var(--text-muted); font-size:13px; }
.stats b { color:var(--text); }
.mini { margin-top:10px; color:var(--text-muted); font-size:12px; line-height:1.8; }
.chart { width:100%; height:260px; background:var(--panel-2); border:1px solid var(--border); border-radius:8px; }
.chart.tall { height:340px; }
.table-wrap { max-height:420px; overflow:auto; }
table { width:100%; border-collapse:collapse; font-size:13px; font-variant-numeric:tabular-nums; }
th,td { padding:6px 10px; text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
th { position:sticky; top:0; background:var(--panel-2); color:var(--text-muted); font-weight:500; }
th:first-child, td:first-child { text-align:left; }
.up{color:var(--up);} .down{color:var(--down);} .flat{color:var(--flat);} .error{color:var(--up);}
.mini-btn { background:var(--panel-2); color:var(--text-muted); border:1px solid var(--border);
  border-radius:4px; padding:2px 8px; cursor:pointer; font-size:12px; margin-left:auto; }
.mini-btn.active { color:#fff; background:var(--accent); border-color:var(--accent); }
.overlay { position:fixed; inset:0; background:rgba(14,17,23,.78); color:var(--text);
  display:none; align-items:center; justify-content:center; font-size:15px; z-index:20; }
.overlay.show { display:flex; }
```

- [ ] **Step 5: 运行测试确认失败（app.js 未创建）**

Run: `python3 -m pytest tests/test_frontend_assets.py -v`
Expected: FAIL（`app.js` 缺失）

---

## Task 17: 前端渲染逻辑（3 屏 + ECharts）

**Files:**
- Create: `frontend/app.js`
- Test: `tests/test_frontend_assets.py`（Task 16 已建）

**Interfaces:**
- Consumes: 快照 JSON（spec §6）、ECharts 全局。
- Produces: `load(force)`、各 `render*`；`setFlowSort(mode)` 全局函数。

- [ ] **Step 1: 写 `frontend/app.js`**

```javascript
const state = { charts: {}, flowSort: "net", snap: null };
const AXIS = { axisLine: { lineStyle: { color: "#2a3141" } }, splitLine: { lineStyle: { color: "#1e2430" } } };

function cls(v){ return v>0?"up":v<0?"down":"flat"; }
function fmt(v,d=2){ return v===null||v===undefined?"--":Number(v).toFixed(d); }
function fmtPct(v){ return v===null||v===undefined?"--":`${v>0?"+":""}${Number(v).toFixed(2)}%`; }
function fmtYi(v){ return v===null||v===undefined?"--":`${Number(v).toLocaleString("zh-CN",{maximumFractionDigits:2})} 亿`; }
function esc(s){ return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function card(name,value,sub,klass=""){ return `<div class="card"><div class="name">${esc(name)}</div>
  <div class="val ${klass}">${value}</div><div class="sub ${klass}">${sub||""}</div></div>`; }
function err(html){ return `<span class="error">⚠ 数据源异常：${esc(html)}</span>`; }

function chart(id, tall) {
  if (state.charts[id]) state.charts[id].dispose();
  state.charts[id] = echarts.init(document.getElementById(id), "dark");
  return state.charts[id];
}

function renderOverseas(s){
  const box = document.getElementById("overseas-cards");
  if (s.error) { box.innerHTML = err(s.error); return; }
  let html = "";
  (s.us_indices||[]).forEach(i => html += card(i.name, fmt(i.close), fmtPct(i.change_pct), cls(i.change_pct)));
  (s.futures||[]).forEach(f => html += card(f.name, fmt(f.price), fmtPct(f.change_pct), cls(f.change_pct)));
  (s.hk_indices||[]).forEach(h => html += card(h.name, fmt(h.price), fmtPct(h.change_pct), cls(h.change_pct)));
  if (s.sox && s.sox.value !== undefined) html += card("费城半导体", fmt(s.sox.value), fmtPct(s.sox.change_pct), cls(s.sox.change_pct));
  if (s.usd_cny && s.usd_cny.mid !== undefined) html += card("美元(中行)", fmt(s.usd_cny.mid, 4), s.usd_cny.note||"", "");
  box.innerHTML = html;
}

function renderAIndex(s){
  const box = document.getElementById("a-cards");
  if (s.error) { box.innerHTML = err(s.error); document.getElementById("a-stats").innerHTML=""; return; }
  box.innerHTML = (s.indices||[]).map(i => card(i.name, fmt(i.price), fmtPct(i.change_pct), cls(i.change_pct))).join("");
  const b = s.breadth||{}, t = s.turnover||{};
  const delta = t.delta;
  const deltaStr = delta===null||delta===undefined ? "--" : `${delta>0?"放量":"缩量"} ${fmtYi(Math.abs(delta))}`;
  document.getElementById("a-stats").innerHTML =
    `两市成交额：<b>${fmtYi(t.total)}</b>（较上日 ${deltaStr}）　` +
    `涨跌家数：<b class="up">涨 ${b.up??"--"}</b> / <b class="down">跌 ${b.down??"--"}</b>`;

  const hist = (s.history&&s.history["sh000001"])||[];
  chart("chart-index").setOption({
    tooltip:{trigger:"axis"}, grid:{left:56,right:16,top:16,bottom:24},
    xAxis:{type:"category",data:hist.map(h=>h.date),...AXIS},
    yAxis:{type:"value",scale:true,...AXIS},
    series:[
      {type:"line",data:hist.map(h=>h.close),smooth:true,showSymbol:false,lineStyle:{color:"#3b82f6",width:2},areaStyle:{color:"rgba(59,130,246,.15)"}},
      {type:"bar",data:hist.map(h=>h.volume),itemStyle:{color:"rgba(245,196,81,.5)"},yAxisIndex:0}
    ]
  });

  const dist = b.distribution||[];
  chart("chart-dist").setOption({
    tooltip:{trigger:"axis"}, grid:{left:40,right:16,top:16,bottom:24},
    xAxis:{type:"category",data:dist.map(d=>d.label),...AXIS},
    yAxis:{type:"value",...AXIS},
    series:[{type:"bar",data:dist.map(d=>({value:d.count,
      itemStyle:{color:(d.label.startsWith("-")||d.label.startsWith("≤"))?"#22c55e":"#ff4d4f"}}))}]
  });
}

function renderSentiment(s){
  const box = document.getElementById("sentiment-cards");
  if (s.error) { box.innerHTML = err(s.error); return; }
  box.innerHTML =
    card("涨停", s.limit_up, "", "up") + card("跌停", s.limit_down, "", "down") +
    card("炸板", `${s.zbgc}`, `炸板率 ${s.zbgc_rate===null?"--":(s.zbgc_rate*100).toFixed(1)+"%"}`) +
    card("最高连板", s.max_boards===null?"--":`${s.max_boards} 板`) +
    card("晋级率", s.promotion_rate===null?"--":`${(s.promotion_rate*100).toFixed(1)}%`, `昨涨停 ${s.prev_limit_up_count}`);
  document.getElementById("sentiment-top").innerHTML =
    "高连板：" + (s.top_boards||[]).map(t=>`${esc(t.name)}(${t.boards}板·${esc(t.industry)})`).join("　");
}

function renderFlow(s){
  if (s.error) {
    document.getElementById("concept-table").innerHTML = `<tbody><tr><td class="error">${esc(s.error)}</td></tr></tbody>`;
    document.getElementById("ths-table").innerHTML = "";
    return;
  }
  const concepts = (s.concepts||[]).slice();
  if (state.flowSort === "chg") concepts.sort((a,b)=>(b.change_pct||-999)-(a.change_pct||-999));
  else concepts.sort((a,b)=>(b.net_inflow||-1e18)-(a.net_inflow||-1e18));
  const head = ["概念","涨跌幅","净额(亿)","领涨股"];
  const top = concepts.slice(0,10), bottom = concepts.slice(-10).reverse();
  const row = c => `<tr><td>${esc(c.name)}</td><td class="${cls(c.change_pct)}">${fmtPct(c.change_pct)}</td>
    <td class="${cls(c.net_inflow)}">${fmt(c.net_inflow)}</td><td>${esc(c.leader)} ${fmtPct(c.leader_change_pct)}</td></tr>`;
  document.getElementById("concept-table").innerHTML =
    `<thead><tr>${head.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>` +
    `<tr><td colspan="4" class="up">净流入 Top10</td></tr>` + top.map(row).join("") +
    `<tr><td colspan="4" class="down">净流出 Top10</td></tr>` + bottom.map(row).join("") + "</tbody>";

  const inds = s.industries||[];
  const ihead = ["行业","涨跌幅","净流入(亿)","上涨","下跌","领涨股"];
  const irows = inds.slice(0,60).map(i=>`<tr><td>${esc(i.name)}</td>
    <td class="${cls(i.change_pct)}">${fmtPct(i.change_pct)}</td>
    <td class="${cls(i.net_inflow)}">${fmt(i.net_inflow)}</td>
    <td class="up">${i.up_count??"--"}</td><td class="down">${i.down_count??"--"}</td>
    <td>${esc(i.leader)}</td></tr>`).join("");
  document.getElementById("ths-table").innerHTML =
    `<thead><tr>${ihead.map(h=>`<th>${h}</th>`).join("")}</tr></thead><tbody>${irows}</tbody>`;

  document.querySelectorAll(".mini-btn").forEach(b=>b.classList.toggle("active", b.dataset.sort===state.flowSort));
}

function setFlowSort(mode){ state.flowSort = mode; if (state.snap) renderFlow(state.snap.sector_flow||{}); }

function renderTreemap(s){
  if (s.error) return;
  const data = (s.industries||[]).map(i=>({name:i.name, value:i.amount||1, change_pct:i.change_pct}));
  chart("chart-treemap", true).setOption({
    tooltip:{formatter: p => `${p.name}<br/>成交额 ${fmtYi(p.value)}<br/>涨跌幅 ${fmtPct(p.data.change_pct)}`},
    visualMap:{min:-3,max:3,calculable:false,orient:"horizontal",left:"center",bottom:0,
      inRange:{color:["#22c55e","#1e2430","#ff4d4f"]}, textStyle:{color:"#8b93a7"}},
    series:[{type:"treemap",roam:false,nodeClick:false,breadcrumb:{show:false},
      itemStyle:{borderColor:"#0e1117",gapWidth:2},
      label:{color:"#e6e9ef",fontSize:12},
      data:data}]
  });
}

function renderNorth(s){
  const box = document.getElementById("north-cards");
  if (s.error) { box.innerHTML = err(s.error); return; }
  let html = card("北向合计", `${s.total_net_buy>0?"+":""}${fmt(s.total_net_buy)} 亿`, "", cls(s.total_net_buy));
  (s.summary||[]).forEach(x=>html += card(x.board, `${x.net_buy>0?"+":""}${fmt(x.net_buy)} 亿`,
    `涨 ${x.up}/平 ${x.flat}/跌 ${x.down}`, cls(x.net_buy)));
  box.innerHTML = html;
  const hist = s.history||[];
  chart("chart-north").setOption({
    tooltip:{trigger:"axis"}, grid:{left:56,right:16,top:16,bottom:24},
    xAxis:{type:"category",data:hist.map(h=>h.date),...AXIS}, yAxis:{type:"value",...AXIS},
    series:[{type:"bar",data:hist.map(h=>({value:h.net_buy,itemStyle:{color:h.net_buy>=0?"#ff4d4f":"#22c55e"}}))}]
  });
}

function renderCapital(s){
  const main = document.getElementById("capital-cards");
  const margin = document.getElementById("margin-cards");
  if (s.error) { main.innerHTML = err(s.error); margin.innerHTML = err(s.error); return; }
  main.innerHTML = card("主力净流入", `${s.main_net_inflow>0?"+":""}${fmtYi(s.main_net_inflow)}`, "", cls(s.main_net_inflow));
  margin.innerHTML = card("融资融券余额", fmtYi(s.margin_total), "", "");
  if (s.notes && s.notes.length) main.innerHTML += `<div class="mini">${s.notes.map(esc).join("<br/>")}</div>`;
}

function renderStatus(sources){
  const total = Object.keys(sources||{}).length;
  const ok = Object.values(sources||{}).filter(v=>v==="ok").length;
  document.getElementById("srcstatus").textContent = `数据源：${ok}/${total} ok`;
}

function renderAll(snap){
  state.snap = snap;
  document.getElementById("meta").textContent =
    `快照 ${snap.date} · 生成 ${(snap.generated_at||"").replace("T"," ").slice(0,19)}`;
  renderStatus(snap.sources);
  renderOverseas(snap.overseas||{});
  renderAIndex(snap.a_index||{});
  renderSentiment(snap.sentiment||{});
  renderFlow(snap.sector_flow||{});
  renderTreemap(snap.sw_industry||{});
  renderNorth(snap.northbound||{});
  renderCapital(snap.capital||{});
}

async function load(force){
  const overlay = document.getElementById("overlay");
  const btn = document.getElementById("refresh");
  overlay.classList.add("show"); btn.disabled = true;
  try {
    const res = force ? await fetch("/api/refresh",{method:"POST"}) : await fetch("/api/snapshot");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    renderAll(await res.json());
  } catch(e) {
    document.getElementById("meta").textContent = `加载失败：${e.message}`;
  } finally {
    overlay.classList.remove("show"); btn.disabled = false;
  }
}

document.getElementById("refresh").addEventListener("click", ()=>load(true));
window.addEventListener("resize", ()=>Object.values(state.charts).forEach(c=>c.resize()));
load(false);
```

- [ ] **Step 2: 运行测试确认通过**

Run: `python3 -m pytest tests/test_frontend_assets.py -v`
Expected: PASS

---

## Task 18: 启动脚本、README、联网冒烟、端到端验收

**Files:**
- Create: `run.sh`, `README.md`, `pytest.ini`, `tests/test_network_smoke.py`

**Interfaces:**
- Consumes: 全部模块。

- [ ] **Step 1: 写 `pytest.ini`**

```ini
[pytest]
markers =
    network: 需要联网的冒烟测试
addopts = -m "not network"
```

- [ ] **Step 2: 写 `run.sh`**

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
export DASHBOARD_MIN_INTERVAL="${DASHBOARD_MIN_INTERVAL:-0.8}"
python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload
```

- [ ] **Step 3: 写 `tests/test_network_smoke.py`**

```python
import pytest

pytestmark = pytest.mark.network


def test_real_snapshot_builds():
    from backend.core.net import force_ipv4
    force_ipv4()
    from backend.fetchers.a_index import fetch_a_index
    out = fetch_a_index()
    assert out["indices"], "应至少返回一个指数"
```

- [ ] **Step 4: 写 `README.md`**

```markdown
# 股市脉搏看板

基于 akshare + FastAPI + ECharts 的本地每日复盘看板（深色盘面风，3 屏）。

## 安装
```bash
pip3 install --user -r requirements.txt
```

## 运行
```bash
chmod +x run.sh && ./run.sh
# 浏览器打开 http://127.0.0.1:8000
```

## 测试
```bash
python3 -m pytest -v            # 单元测试（不联网）
python3 -m pytest -m network -v # 联网冒烟
```

## 三屏
- 屏一 市场全局与情绪：外围风向 / A股量能(含放缩量) / 情绪博弈(涨跌停·炸板率·连板·晋级率) / 涨跌分布
- 屏二 资金主线与板块轮动：概念资金流 Top / 申万一级热力图 / 同花顺行业(90)
- 屏三 长线资金：北向资金 / 主力资金 / 融资融券

## 已知限制
- 东财 `clist/get` 批量接口在当前网络被封，改用新浪/同花顺/乐咕/交易所 + 东财 push2ex/datacenter。
- 深交所成交/两融接口异常，相关值可能缺失。
- 无离岸 CNH 稳定源，用中行美元牌价代理。
- 本版为每日快照，不做盘中实时刷新。
```

- [ ] **Step 5: 安装依赖并跑全部单元测试**

Run:
```bash
pip3 install --user -r requirements.txt
python3 -m pytest -v
```
Expected: 全部单元测试 PASS（network 用例默认跳过）

- [ ] **Step 6: 端到端冒烟（可选，联网）**

Run: `python3 -m pytest -m network tests/test_network_smoke.py -v`
Expected: 视网络情况 PASS；若临时限流失败则记录。

- [ ] **Step 7: 启动并人工验收**

Run: `./run.sh`，浏览器打开 `http://127.0.0.1:8000`，确认：3 屏渲染、情绪卡/热力图/直方图/概念 Top 正常、刷新按钮可重抓、深色主题正确、顶栏数据源状态显示。

---

## 自检（Self-Review）

**Spec 覆盖**
- §4 网络层 → Task 2/3/4/5。
- §5.1 overseas → Task 9；§5.2 a_index → Task 8；§5.3 sentiment → Task 10；§5.4 northbound → Task 11；§5.5 sw_industry → Task 12；§5.6 sector_flow → Task 13；§5.7 capital → Task 14；§5.8 snapshot(含 delta) → Task 7。
- §6 schema → Task 7 + 各 fetcher 输出键 + Task 15 sources。
- §7 API → Task 15。
- §8 前端 3 屏 + Treemap + 直方图 + 令牌 → Task 16/17。
- §9 错误处理 → Task 7/13/14/15/17。
- §10 测试 → 各任务测试 + Task 18 冒烟。
- §13 里程碑 → M1=Task1–8、M2=Task9–14、M3=Task15–17、M4=Task18。

**占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码。

**类型/键一致性**
- `fetch(fn, *args, source=..., use_cache=...)` 全部 fetcher 一致。
- 快照分区键 `overseas/a_index/sentiment/northbound/sw_industry/sector_flow/capital` 在 Task 15 `DEFAULT_FETCHERS`、Task 17 `renderAll`、Task 16 HTML 区块一致。
- `build_snapshot(fetchers, data_dir, date)` / `get_or_create(fetchers, data_dir, date, force)` 在 Task 7 与 Task 15 一致。
- `turnover.prev_total/delta` 在 Task 7 写入、Task 17 `renderAIndex` 读取，字段名一致。
- `zbgc_rate/promotion_rate/max_boards/top_boards` 在 Task 10 产生、Task 17 `renderSentiment` 读取，字段名一致。
