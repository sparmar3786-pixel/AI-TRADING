"""Read-only dashboard app factory. No unauthenticated start/stop/order controls."""
from __future__ import annotations
import hmac
import json
from typing import Callable, Any

HTML = """<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>AI Trading Status</title><style>body{font:16px system-ui;background:#0b1220;color:#e5e7eb;margin:2rem}main{max-width:900px;margin:auto}pre{white-space:pre-wrap;background:#111827;padding:1rem;border-radius:12px}</style></head><body><main><h1>AI Trading · Read-only status</h1><p>Paper/research status only. No order controls are exposed here.</p><pre id='status'>Loading…</pre></main><script>async function refresh(){try{const r=await fetch('/level2/status');if(!r.ok)throw Error('HTTP '+r.status);document.querySelector('#status').textContent=JSON.stringify(await r.json(),null,2)}catch(e){document.querySelector('#status').textContent='Status unavailable: '+e.message}}refresh();setInterval(refresh,5000)</script></body></html>"""

def create_dashboard_app(status_provider: Callable[[], Any], access_token: str):
    if not access_token: raise ValueError("dashboard access token is required")
    try:
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as exc: raise RuntimeError("FastAPI is required to mount the dashboard") from exc
    app = FastAPI(title="AI-TRADING Level-2 Dashboard", docs_url=None, redoc_url=None)
    def authorize(authorization: str | None):
        expected = "Bearer " + access_token
        if authorization is None or not hmac.compare_digest(authorization, expected): raise HTTPException(status_code=401, detail="unauthorized")
    @app.get("/level2/dashboard", response_class=HTMLResponse)
    def dashboard(authorization: str | None = Header(default=None)):
        authorize(authorization); return HTML
    @app.get("/level2/status")
    def status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        value = status_provider()
        if hasattr(value, "model_dump"): value = value.model_dump()
        if not isinstance(value, (dict, list, str, int, float, bool, type(None))): value = str(value)
        return json.loads(json.dumps(value, default=str))
    return app
