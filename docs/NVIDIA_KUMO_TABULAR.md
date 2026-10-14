# NVIDIA Kumo Tabular NIM integration

This integration is in **AI-TRADING**, not Fresh-Apk.

## Architecture and limits

- `backend/app/kumo_nim_api.py` exposes a server-side proxy to NVIDIA Kumo Tabular NIM.
- `GET /v1/ai/kumo/status` checks `/v1/health/ready` on the configured NIM host.
- `POST /v1/ai/kumo/predict` forwards structured rows to `/v1/predictions`.
- The NIM container must run on a reachable NVIDIA GPU host. The Railway Python API does not provide a GPU just because this proxy is deployed.
- Kumo Tabular is for structured/tabular predictions, **not general-purpose chat**. It cannot safely replace Gemini's conversational capability by itself. The chat provider remains separate until another chat-capable provider is selected.
- Prediction output is not an order or an approved trading signal. Keep the deterministic quant, data-freshness, and risk gates authoritative. No broker order endpoint is enabled here.

## Railway variables

Set these on the AI-TRADING backend service, never in the APK or committed source:

- `KUMO_NIM_BASE_URL`: private/reachable base URL of the GPU-hosted Kumo NIM service, e.g. `https://your-private-nim-host` (no trailing slash required).
- `KUMO_NIM_API_KEY`: optional bearer token if the NIM gateway requires one.

Do not set these to the NVIDIA registry login token. The NGC token is only for pulling the container image and must not be sent to the prediction endpoint. If an NGC token was shared in chat or committed anywhere, revoke and rotate it.

## GPU host

Run the NVIDIA-published Kumo Tabular NIM image on an NVIDIA GPU host using the exact tag and hardware/runtime requirements supported by your NGC account. Confirm that the host can pull the image, has working NVIDIA Container Toolkit / `--gpus all`, and exposes the NIM API only over a private network or authenticated TLS gateway. Do not assume Railway supports this GPU container.

## Example request

Use a real, validated trading feature schema—not the customer-renewal sample:

```json
{
  "data": [
    {
      "symbol": "NIFTY",
      "timeframe": "5m",
      "return_1": 0.0012,
      "return_3": 0.0021,
      "rsi_14": 56.4,
      "atr_pct": 0.003,
      "pcr": 1.08,
      "depth_imbalance": 0.12
    }
  ]
}
```

The feature names above are illustrative only; the active Kumo model's schema and trained target must match before this can be used for a trading decision.

## Verification checklist

1. Configure the GPU NIM host and Railway variables.
2. Call `GET /v1/ai/kumo/status` with a valid `X-Device-Id` (43–128 URL-safe characters).
3. Require `ready: true` from the live health check.
4. Send a schema-valid feature row to `POST /v1/ai/kumo/predict`.
5. Confirm a real prediction response, latency, and schema compatibility.
6. Add offline tests and an end-to-end staging test before promoting the provider in UI.

Until steps 2–5 pass, the provider must be shown as unconfigured/unverified, not green.
