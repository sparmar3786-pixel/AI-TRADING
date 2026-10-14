"""NVIDIA Kumo Tabular NIM proxy for structured trading-feature inference.

The NIM container must run on a separate NVIDIA-GPU host. This API never
pretends a model is ready unless KUMO_NIM_BASE_URL is configured and a live
health request succeeds. It never places broker orders.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

try:
    from app.main import _device
except ImportError:
    # Tests importing backend.app.kumo_nim_api do not need to import main here.
    def _device() -> str:
        return ""

router = APIRouter(tags=["NVIDIA Kumo Tabular"])
DEFAULT_TIMEOUT_SECONDS = 20
MAX_REQUEST_BYTES = 512_000


class KumoPredictionRequest(BaseModel):
    # This is deliberately a generic structured table payload. Use real,
    # validated trading feature rows; do not send customer-renewal demo data.
    data: list[dict[str, Any]] = Field(min_length=1, max_length=256)
    model: str | None = Field(default=None, max_length=128)


def _base_url() -> str:
    return os.getenv("KUMO_NIM_BASE_URL", "").strip().rstrip("/")


def _call_nim(path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any, float]:
    base = _base_url()
    if not base:
        raise HTTPException(
            status_code=503,
            detail="Kumo NIM is not configured. Set KUMO_NIM_BASE_URL to the private/reachable GPU host URL.",
        )
    if not base.startswith(("https://", "http://")):
        raise HTTPException(status_code=503, detail="KUMO_NIM_BASE_URL must be an http(s) URL.")
    url = base + path
    headers = {"Accept": "application/json", "User-Agent": "AI-TRADING-Kumo-Proxy/1.0"}
    token = os.getenv("KUMO_NIM_API_KEY", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Kumo request exceeds 512 KB.")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=502, detail="Kumo NIM response exceeds 512 KB.")
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, parsed, round((time.perf_counter() - started) * 1000, 2)
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        # Do not forward raw upstream bodies: they may contain sensitive data.
        raise HTTPException(status_code=502, detail=f"Kumo NIM returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Kumo NIM is unreachable or returned invalid JSON.") from exc


@router.get("/v1/ai/kumo/status")
def kumo_status(_: str = Depends(_device)) -> dict[str, Any]:
    if not _base_url():
        return {
            "provider": "nvidia_kumo_tabular",
            "status": "not_configured",
            "configured": False,
            "ready": False,
            "capability": "structured_tabular_prediction",
            "general_chat_supported": False,
            "message": "Set KUMO_NIM_BASE_URL to a reachable GPU-hosted Kumo NIM endpoint.",
        }
    try:
        code, data, elapsed = _call_nim("/v1/health/ready")
        ready = 200 <= code < 300
        return {
            "provider": "nvidia_kumo_tabular",
            "status": "ready" if ready else "unhealthy",
            "configured": True,
            "ready": ready,
            "latency_ms": elapsed,
            "upstream": data if isinstance(data, dict) else {"response": str(data)[:200]},
            "capability": "structured_tabular_prediction",
            "general_chat_supported": False,
        }
    except HTTPException as exc:
        return {
            "provider": "nvidia_kumo_tabular",
            "status": "unreachable",
            "configured": True,
            "ready": False,
            "capability": "structured_tabular_prediction",
            "general_chat_supported": False,
            "message": str(exc.detail),
        }


@router.post("/v1/ai/kumo/predict")
def kumo_predict(body: KumoPredictionRequest, _: str = Depends(_device)) -> dict[str, Any]:
    """Proxy a structured feature batch to Kumo NIM; no fabricated fallback."""
    payload: dict[str, Any] = {"data": body.data}
    if body.model:
        payload["model"] = body.model
    code, result, elapsed = _call_nim("/v1/predictions", payload)
    if not 200 <= code < 300:
        raise HTTPException(status_code=502, detail="Kumo NIM prediction failed.")
    return {
        "status": "ok",
        "provider": "nvidia_kumo_tabular",
        "task": "structured_tabular_prediction",
        "latency_ms": elapsed,
        "result": result,
        "signal_only": True,
        "order_placement_enabled": False,
        "note": "Prediction is model output, not a trade instruction; validate with the deterministic quant and risk gates.",
    }
