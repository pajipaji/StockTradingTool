import logging
from pathlib import Path
import backend.core.logging as logging_module
from backend.core.logging import setup_logging, get_logger


def test_setup_logging_writes_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(logging_module, "_CONFIGURED", False)
    setup_logging(tmp_path, level=logging.INFO)
    log = get_logger("test.logger")
    log.info("hello-dashboard")
    for h in logging.getLogger().handlers:
        h.flush()
    content = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "hello-dashboard" in content


def test_setup_logging_is_idempotent(tmp_path: Path):
    setup_logging(tmp_path, level=logging.INFO)
    root = logging.getLogger()
    count = len(root.handlers)
    setup_logging(tmp_path, level=logging.INFO)
    assert len(root.handlers) == count
