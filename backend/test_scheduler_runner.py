import importlib.util
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parent / "scripts/check_due_watches.py"
    spec = importlib.util.spec_from_file_location("check_due_watches", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, limit):
        return json.dumps(self.payload).encode()


def test_scheduler_requires_api_key(monkeypatch):
    mod = _load()
    monkeypatch.delenv("FIND_THE_REST_API_KEY", raising=False)
    monkeypatch.setenv("FINDREST_SCHEDULER_BASE_URL", "https://api.example")
    err = io.StringIO()
    with redirect_stderr(err):
        code = mod.run()
    assert code == 2
    assert "API_KEY" in err.getvalue()


def test_scheduler_uses_header_and_logs_only_aggregate_counts(monkeypatch):
    mod = _load()
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "top-secret")
    monkeypatch.setenv("FINDREST_SCHEDULER_BASE_URL", "https://api.example")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return FakeResponse({
            "checked": 2,
            "found": 1,
            "remaining_active": 8,
            "items": [
                {"watch_id": "private-id-1", "checked": True, "found": True, "best_match_url": "https://secret.example/match"},
                {"watch_id": "private-id-2", "checked": True, "found": False},
            ],
        })

    monkeypatch.setattr(mod, "urlopen", fake_urlopen)
    out = io.StringIO()
    with redirect_stdout(out):
        code = mod.run()

    assert code == 0
    assert captured["url"] == "https://api.example/v1/watches/check-due"
    assert captured["headers"]["X-findtherest-key"] == "top-secret"
    logged = out.getvalue()
    assert "checked=2" in logged and "found=1" in logged
    assert "top-secret" not in logged
    assert "private-id" not in logged
    assert "secret.example" not in logged


def test_scheduler_partial_batch_failure_exits_nonzero(monkeypatch):
    mod = _load()
    monkeypatch.setenv("FIND_THE_REST_API_KEY", "secret")
    monkeypatch.setenv("FINDREST_SCHEDULER_HOSTPORT", "find-the-rest-api:10000")
    monkeypatch.delenv("FINDREST_SCHEDULER_BASE_URL", raising=False)

    monkeypatch.setattr(mod, "urlopen", lambda request, timeout: FakeResponse({
        "checked": 1,
        "found": 0,
        "remaining_active": 4,
        "items": [
            {"checked": True, "found": False},
            {"checked": False, "found": False, "error": "RuntimeError"},
        ],
    }))
    assert mod.run() == 5


def test_render_blueprint_wires_hourly_cron_to_api():
    root = Path(__file__).resolve().parents[1]
    text = (root / "render.yaml").read_text()
    assert "type: cron" in text
    assert "name: find-the-rest-watch-scheduler" in text
    assert 'schedule: "5 * * * *"' in text
    assert "python scripts/check_due_watches.py" in text
    assert "property: hostport" in text
    assert "envVarKey: FIND_THE_REST_API_KEY" in text
