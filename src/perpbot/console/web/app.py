from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse

from ..console_state import ConsoleState
from .web_app import create_web_app
from ...exposure.exposure_model import ExposureModel
from ...health.health_monitor import HealthMonitor


class _NullCapitalOrchestrator:
    def get_snapshot(self):
        return None


class _NullExposureService:
    def get_global_exposure(self) -> ExposureModel:
        return ExposureModel.empty()


def create_app() -> FastAPI:
    console_state = ConsoleState(
        execution_engine=None,
        quote_engine=None,
        exposure_service=_NullExposureService(),
        capital_orchestrator=_NullCapitalOrchestrator(),
    )
    health_monitor = HealthMonitor(console_state)

    app = create_web_app(health_monitor, console_state)

    def _index_html() -> str:
        return """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PerpBot UI</title>
    <style>
      body { font-family: Arial, sans-serif; background:#0b1021; color:#e9edf5; margin:0; padding:20px; }
      .card { background:#11182f; border:1px solid #1b2647; border-radius:10px; padding:14px; max-width:980px; }
      .row { display:grid; grid-template-columns: 1fr 1fr; gap:10px; }
      pre { background:#0f172a; border:1px solid #1f2a52; padding:10px; border-radius:8px; white-space:pre-wrap; word-break:break-word; }
      .muted { color:#9aa5c2; font-size:12px; }
      a { color:#7ea8ff; }
      .pill { display:inline-block; padding:4px 8px; border-radius:999px; background:#1f2a52; font-size:12px; }
    </style>
  </head>
  <body>
    <div class="card">
      <h2 style="margin-top:0">PerpBot Web</h2>
      <div class="muted">
        <span class="pill" id="ws">WS: 连接中</span>
        · <a href="/health">/health</a>
        · <a href="/state">/state</a>
        · <a href="/metrics">/metrics</a>
      </div>
      <div class="row" style="margin-top:12px">
        <div>
          <div class="muted">Health Snapshot</div>
          <pre id="health">加载中...</pre>
        </div>
        <div>
          <div class="muted">Console State</div>
          <pre id="state">加载中...</pre>
        </div>
      </div>
    </div>
    <script>
      const render = (id, obj) => {
        document.getElementById(id).textContent =
          typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
      };
      const wsPill = document.getElementById('ws');
      function connect() {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const ws = new WebSocket(`${proto}://${window.location.host}/ws/stream`);
        ws.onopen = () => { wsPill.textContent = 'WS: 已连接'; };
        ws.onclose = () => { wsPill.textContent = 'WS: 重连中'; setTimeout(connect, 1000); };
        ws.onerror = () => ws.close();
        ws.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data);
            render('health', data.health_snapshot || { message: 'health snapshot not ready' });
            render('state', data.console_state || {});
          } catch (e) {}
        };
      }
      connect();
      fetch('/health').then(r => r.json()).then(j => render('health', j)).catch(() => {});
      fetch('/state').then(r => r.json()).then(j => render('state', j)).catch(() => {});
    </script>
  </body>
</html>"""

    @app.get("/", response_class=HTMLResponse)
    def _index() -> str:
        return _index_html()

    @app.get("/ui/v2/dashboard", response_class=HTMLResponse)
    def _ui_v2_dashboard() -> str:
        return _index_html()

    @app.get("/ui/v2")
    def _ui_v2_root() -> RedirectResponse:
        return RedirectResponse(url="/ui/v2/dashboard")

    @app.on_event("startup")
    def _startup() -> None:  # pragma: no cover - framework hook
        health_monitor.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:  # pragma: no cover - framework hook
        health_monitor.stop()

    return app


app = create_app()
