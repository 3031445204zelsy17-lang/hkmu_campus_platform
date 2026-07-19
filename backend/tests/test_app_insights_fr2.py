"""FR2 regression: _init_app_insights must wire FastAPIInstrumentor so per-request
spans reach AppRequests.

Root cause (fixed): the FastAPI instrumentor subpackage wasn't in requirements,
and the distro's auto-instrument timing misses an app created *before*
configure_azure_monitor runs (our app exists at lifespan startup). Result:
AppRequests was 0 while AppTraces (logging) worked — exactly the partial-telemetry
symptom we saw on prod (sec_audit 401 reached AppTraces, but no request ever
reached AppRequests).

These tests fake the instrumentor + distro modules (neither may be installed
locally) to assert instrument_app is called when a connection string is set,
and NOT called when it's absent (dormant default preserved).
"""
import sys
import types


def _install_fakes(monkeypatch, instrumentor_calls):
    """Inject fake azure.monitor.opentelemetry + opentelemetry.instrumentation.fastapi
    so _init_app_insights runs without the real packages installed locally."""
    fake_distro = types.ModuleType("azure.monitor.opentelemetry")
    fake_distro.configure_azure_monitor = lambda *a, **kw: None
    monkeypatch.setitem(sys.modules, "azure.monitor.opentelemetry", fake_distro)

    fake_fastapi = types.ModuleType("opentelemetry.instrumentation.fastapi")

    class FakeInstrumentor:
        @staticmethod
        def instrument_app(app):
            instrumentor_calls.append(app)

    fake_fastapi.FastAPIInstrumentor = FakeInstrumentor
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.fastapi", fake_fastapi)


def test_init_app_insights_instruments_fastapi_when_configured(monkeypatch):
    """Connection string set → FastAPIInstrumentor.instrument_app called.

    v2 also invokes _init_app_insights at import time (top-level call at the
    tail of main.py), so importing main can itself append to `calls`; we use a
    fresh app and clear first to isolate the function-under-test.
    """
    calls = []
    _install_fakes(monkeypatch, calls)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=fake")

    from backend.app.main import _init_app_insights
    from fastapi import FastAPI

    fresh_app = FastAPI()
    calls.clear()  # ignore any import-time top-level call
    _init_app_insights(fresh_app)
    assert len(calls) == 1, (
        "FastAPIInstrumentor.instrument_app must be called when configured — "
        "if 0, the FR2 regression returned (AppRequests would stay empty)"
    )
    assert calls[0] is fresh_app


def test_init_app_insights_dormant_without_connection_string(monkeypatch):
    """No connection string → instrument_app NOT called (dormant default)."""
    calls = []
    _install_fakes(monkeypatch, calls)
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)

    from backend.app.main import app, _init_app_insights

    _init_app_insights(app)
    assert calls == [], "instrument_app must not run without a connection string"
