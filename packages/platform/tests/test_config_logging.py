import json

from fsp_platform.config import BaseServiceSettings
from fsp_platform.logging import configure_logging, get_correlation_id, set_correlation_id


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("ENV", "demo")
    monkeypatch.setenv("ML_FAKE", "true")
    s = BaseServiceSettings()
    assert s.env == "demo" and s.ml_fake is True


def test_log_json_has_correlation_id(capsys):
    import structlog

    configure_logging("t", "INFO")
    set_correlation_id("abc")
    structlog.get_logger().info("hello", x=1)
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["correlation_id"] == "abc" and line["message"] == "hello" and line["service"] == "t"
    assert get_correlation_id() == "abc"
