from fastapi import FastAPI

from revu.application.app import run_app
from revu.runner import run


def test_run_calls_run_app(monkeypatch):
    called = {}

    def fake_run_app():
        called["run_app"] = True

    monkeypatch.setattr("revu.runner.run_app", fake_run_app)

    run()

    assert called["run_app"]


def test_run_app_starts_uvicorn_with_correct_params(monkeypatch):
    called = {}

    def fake_run(app, **kwargs):
        called["app"] = app
        called["kwargs"] = kwargs

    monkeypatch.setattr("revu.application.app.uvicorn.run", fake_run)

    run_app()

    assert isinstance(called["app"], FastAPI)
    kwargs = called["kwargs"]
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 8000
    assert kwargs["loop"] == "asyncio"
    assert kwargs["log_config"] is None


def test_run_app_honours_configured_host_and_port(monkeypatch, settings):
    called = {}
    settings.set("APP_HOST", "127.0.0.1")
    settings.set("APP_PORT", 9001)

    monkeypatch.setattr("revu.application.app.uvicorn.run", lambda app, **kwargs: called.update(kwargs))

    run_app()

    assert called["host"] == "127.0.0.1"
    assert called["port"] == 9001
