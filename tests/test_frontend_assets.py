from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_files_exist():
    for name in ("index.html", "style.css", "app.js", "vendor/echarts.min.js"):
        assert (ROOT / "frontend" / name).exists(), name


def test_index_references_assets():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "/static/style.css" in html
    assert "/static/app.js" in html and "echarts.min.js" in html
    assert html.index("echarts.min.js") < html.index("/static/app.js")


def test_index_v3_structure():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for marker in ("盘前外围映射", "主线攻防", "复盘笔记"):
        assert marker in html, marker
    assert 'id="note"' in html
    assert 'id="chart-emotion"' in html


def test_index_v4_structure():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for marker in ('id="us-sector-table"', 'id="ladder-cards"', 'id="fin-buy-table"'):
        assert marker in html, marker


def test_index_v5_structure():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    for marker in ('id="us-sector-table"', 'id="ladder-cards"', 'id="emotion-extra"',
                   'id="fin-buy-table"', 'id="fin-sell-table"',
                   'id="style-bars"', 'id="overseas-market"', 'id="overseas-other"'):
        assert marker in html, marker
    assert 'id="north-table"' not in html
    assert 'id="premarket"' not in html


def test_style_has_tokens():
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    for token in ("#0e1117", "#161b26", "#1e2430", "#2a3141", "#e6e9ef",
                  "#8b93a7", "#ff4d4f", "#22c55e", "#3b82f6", "#f5c451"):
        assert token in css, token
