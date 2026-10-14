"""NVIDIA Kumo Tabular proxy for self-hosted NIM and NVIDIA API Catalog."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

DEVICE_ID_RE = __import__("re").compile(r"^[A-Za-z0-9_-]{43,128}$")
NVIDIA_CATALOG_BASE = "https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-tabular"
router = APIRouter(tags=["NVIDIA Kumo Tabular"])
DEFAULT_TIMEOUT_SECONDS = 25
MAX_REQUEST_BYTES = 512_000


def _device(x_device_id: str = Header(default="")) -> str:
    if not DEVICE_ID_RE.fullmatch(x_device_id or ""):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Device-Id")
    return x_device_id


class KumoPredictionRequest(BaseModel):
    # Hosted Catalog requires the full Universal TFM request envelope. The
    # legacy data field remains accepted only for self-hosted proxy compatibility.
    request: dict[str, Any] | None = None
    data: list[dict[str, Any]] | None = Field(default=None, min_length=1, max_length=256)
    model: str | None = Field(default=None, max_length=128)
    index: str | None = Field(default=None, max_length=32)


def _self_hosted_base() -> str:
    return os.getenv("KUMO_NIM_BASE_URL", "").strip().rstrip("/")


def _hosted_key() -> str:
    # Prefer the provider-specific variable; NVIDIA_API_KEY is supported as an alias.
    return (os.getenv("KUMO_NVIDIA_API_KEY") or os.getenv("NVIDIA_API_KEY") or "").strip()


def _http_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None,
               token: str = "") -> tuple[int, Any, float]:
    headers = {"Accept": "application/json", "User-Agent": "AI-TRADING-Kumo-Proxy/1.1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if payload is not None:
        try:
            body = json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Kumo request must be valid finite JSON.") from exc
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="Kumo request exceeds 512 KB.")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_REQUEST_BYTES + 1)
            if len(raw) > MAX_REQUEST_BYTES:
                raise HTTPException(status_code=502, detail="Kumo response exceeds 512 KB.")
            parsed = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, parsed, round((time.perf_counter() - started) * 1000, 2)
    except HTTPException:
        raise
    except urllib.error.HTTPError as exc:
        # Never return upstream bodies: they may include sensitive request details.
        if exc.code in (401, 403):
            detail = "NVIDIA rejected the API key or its permissions."
        elif exc.code in (400, 422):
            detail = "NVIDIA rejected the Kumo request schema or input data."
        elif exc.code == 429:
            detail = "NVIDIA Kumo API rate limit reached."
        else:
            detail = f"NVIDIA Kumo API returned HTTP {exc.code}."
        raise HTTPException(status_code=502, detail=detail) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Kumo endpoint is unreachable or returned invalid JSON.") from exc


def _self_hosted_call(path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any, float]:
    base = _self_hosted_base()
    if not base:
        raise HTTPException(status_code=503, detail="Kumo NIM is not configured.")
    if not base.startswith(("https://", "http://")):
        raise HTTPException(status_code=503, detail="KUMO_NIM_BASE_URL must be an http(s) URL.")
    token = os.getenv("KUMO_NIM_API_KEY", "").strip()
    return _http_json(base + path, method="POST" if payload is not None else "GET", payload=payload, token=token)


@router.get("/v1/ai/kumo/status")
def kumo_status(_: str = Depends(_device)) -> dict[str, Any]:
    # NVIDIA API Catalog is a hosted endpoint: it has a models endpoint, not the
    # self-hosted NIM /v1/health/ready endpoint.
    key = _hosted_key()
    if key:
        try:
            code, data, elapsed = _http_json(NVIDIA_CATALOG_BASE + "/models", token=key)
            return {
                "provider": "nvidia_kumo_tabular",
                "mode": "hosted_api_catalog",
                "status": "ready" if 200 <= code < 300 else "unhealthy",
                "configured": True,
                "ready": 200 <= code < 300,
                "latency_ms": elapsed,
                "upstream": data if isinstance(data, dict) else {},
                "capability": "structured_tabular_prediction",
                "general_chat_supported": False,
            }
        except HTTPException as exc:
            return {
                "provider": "nvidia_kumo_tabular",
                "mode": "hosted_api_catalog",
                "status": "unreachable",
                "configured": True,
                "ready": False,
                "capability": "structured_tabular_prediction",
                "general_chat_supported": False,
                "message": str(exc.detail),
            }
    if not _self_hosted_base():
        return {
            "provider": "nvidia_kumo_tabular",
            "status": "not_configured",
            "configured": False,
            "ready": False,
            "capability": "structured_tabular_prediction",
            "general_chat_supported": False,
            "message": "Set KUMO_NVIDIA_API_KEY for NVIDIA hosted API, or KUMO_NIM_BASE_URL for self-hosted NIM.",
        }
    try:
        code, data, elapsed = _self_hosted_call("/v1/health/ready")
        return {
            "provider": "nvidia_kumo_tabular",
            "mode": "self_hosted_nim",
            "status": "ready" if 200 <= code < 300 else "unhealthy",
            "configured": True,
            "ready": 200 <= code < 300,
            "latency_ms": elapsed,
            "upstream": data if isinstance(data, dict) else {},
            "capability": "structured_tabular_prediction",
            "general_chat_supported": False,
        }
    except HTTPException as exc:
        return {
            "provider": "nvidia_kumo_tabular",
            "mode": "self_hosted_nim",
            "status": "unreachable",
            "configured": True,
            "ready": False,
            "capability": "structured_tabular_prediction",
            "general_chat_supported": False,
            "message": str(exc.detail),
        }


@router.post("/v1/ai/kumo/predict")
def kumo_predict(body: KumoPredictionRequest, _: str = Depends(_device)) -> dict[str, Any]:
    """Proxy real Kumo structured prediction; never places orders or fabricates fallback."""
    hosted_key = _hosted_key()
    if hosted_key:
        payload = body.request
        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=422,
                detail="Hosted Kumo requires the full NVIDIA request envelope in the 'request' field (model, task, schema, context, predict, output).",
            )
        required = {"model", "task", "schema", "context", "predict", "output"}
        if not required.issubset(payload):
            raise HTTPException(status_code=422, detail="Kumo request is missing required fields: model, task, schema, context, predict, output.")
        if payload.get("model") != "kumo-tabular":
            raise HTTPException(status_code=422, detail="Hosted Kumo request model must be 'kumo-tabular'.")
        code, result, elapsed = _http_json(NVIDIA_CATALOG_BASE + "/predictions", method="POST", payload=payload, token=hosted_key)
        mode = "hosted_api_catalog"
    else:
        request_payload = body.request
        if request_payload is None:
            # Preserve the previous proxy contract for callers during migration.
            if not body.data:
                raise HTTPException(status_code=422, detail="Provide a full 'request' envelope for Kumo prediction.")
            request_payload = {"data": body.data}
            if body.model:
                request_payload["model"] = body.model
        code, result, elapsed = _self_hosted_call("/v1/predictions", request_payload)
        mode = "self_hosted_nim"
    if not 200 <= code < 300:
        raise HTTPException(status_code=502, detail="Kumo prediction failed.")
    response: dict[str, Any] = {
        "status": "ok",
        "provider": "nvidia_kumo_tabular",
        "mode": mode,
        "task": "structured_tabular_prediction",
        "latency_ms": elapsed,
        "result": result,
        "signal_only": True,
        "order_placement_enabled": False,
        "note": "Model output is not a trade instruction; validate with deterministic quant, data-quality and risk gates.",
    }
    # Optional, explicit bridge: attach the real Kumo inference to the current
    # deterministic Quant snapshot. Kumo output is evidence only; it never
    # changes the Quant decision or bypasses live-data/risk gates.
    if body.index:
        index = body.index.strip().upper()
        try:
            from app import main as signal_api
        except ImportError:
            from backend.app import main as signal_api
        if index not in signal_api.INDEXES:
            raise HTTPException(status_code=422, detail="Unsupported index for Kumo-to-Quant connection.")
        snapshot = signal_api._get_signals(force=False)
        signal = dict((snapshot.get("signals") or {}).get(index) or {})
        quant = dict(signal.get("quant_engine") or signal.get("five_layer_engine") or {})
        validation = dict(signal.get("live_validation") or {})
        quant["kumo_tabular_evidence"] = {
            "status": "inference_received",
            "provider": "nvidia_kumo_tabular",
            "latency_ms": elapsed,
            "prediction": result,
            "deterministic_gate_verdict": str(validation.get("verdict") or "WAIT"),
            "quant_decision_unchanged": str(quant.get("decision") or signal.get("decision") or "WAIT"),
            "prediction_used_as_trade_authority": False,
        }
        response["quant_connection"] = {
            "connected": True,
            "index": index,
            "signal_decision": str(signal.get("decision") or "WAIT"),
            "quant_decision": str(quant.get("decision") or signal.get("decision") or "WAIT"),
            "deterministic_gate_verdict": str(validation.get("verdict") or "WAIT"),
            "quant_engine": quant,
            "live_validation": validation,
            "decision_changed_by_kumo": False,
            "note": "Real Kumo inference is attached to Quant as external evidence; no trade direction is inferred from undocumented model output.",
        }
    return response
