# NVIDIA Kumo Tabular integration

This integration is in **AI-TRADING**, not Fresh-Apk.

## Hosted NVIDIA API Catalog (recommended first path)

The hosted API endpoint is:

- Base: `https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-tabular`
- Models/status check: `GET /models`
- Prediction: `POST /predictions`

The API key is created from the NVIDIA Kumo Tabular model page: https://build.nvidia.com/nvidia/kumo-tabular

In Railway, open the **AI-TRADING backend service → Variables** and add:

- `KUMO_NVIDIA_API_KEY`: the NVIDIA API Catalog key (recommended variable name).

The backend also accepts `NVIDIA_API_KEY` as a fallback alias, but prefer `KUMO_NVIDIA_API_KEY` so credentials are clearly scoped. Do not put the key in Flutter/APK, commit it to GitHub, log it, or send it in chat.

After redeploy, call `GET /v1/ai/kumo/status` with a valid `X-Device-Id` header (43–128 URL-safe characters). In hosted mode, the status endpoint checks NVIDIA's `/models` endpoint using bearer authentication. This verifies authentication/reachability, not a successful inference.

### Hosted prediction request

`POST /v1/ai/kumo/predict` expects the full NVIDIA Universal TFM request envelope under the `request` property. Optionally include `index` (for example `NIFTY`) to attach the real inference result to that index’s current `quant_engine.kumo_tabular_evidence` snapshot. The request must contain `model`, `task`, `schema`, `context`, `predict`, and `output`; `model` must be `kumo-tabular`. Use NVIDIA's official example and replace its demo data with a validated, representative trading dataset and a defined target:

https://docs.api.nvidia.com/nim/reference/nvidia-kumo-tabular-statuspolling

Example shape (not a complete inference request):

```json
{
  "request": {
    "model": "kumo-tabular",
    "task": {},
    "schema": {},
    "context": {},
    "predict": {},
    "output": {"fields": ["prediction", "probabilities"]}
  }
}
```

Do not send only `{"data":[...]}` to the hosted API. Kumo needs labeled context rows, a task/target definition, a matching schema, and prediction rows. Prediction quality depends on using a suitable target and relevant historical examples; a generic label like UP/DOWN must be properly defined and validated from historical data before use.

## Self-hosted NIM (alternative)

If running your own NIM on a separate compatible NVIDIA GPU host, set:

- `KUMO_NIM_BASE_URL`: reachable base URL of the NIM service, with no trailing slash.
- `KUMO_NIM_API_KEY`: optional bearer token if your gateway requires it.

The self-hosted container exposes `GET /v1/health/ready` and `POST /v1/predictions` on port 8000. The Railway backend itself does not gain a GPU from this proxy.

## Important boundaries

- Kumo Tabular predicts classification labels or regression values from structured tables. It is not a general-purpose chat model and does not replace Gemini/OpenRouter chat.
- A green status only indicates provider API reachability/authentication. Verify a real prediction before marking inference as working.
- Prediction output is not an approved trade. When `index` is supplied, the response includes `quant_connection` with the real model output attached as external evidence, the current deterministic gate verdict, and the unchanged Quant decision. This is deliberately not a trade-direction mapping: Kumo task/target semantics must be explicitly defined and validated before its label can participate in a decision. The bridge does not mutate the cached signal or override WAIT. Keep market-data freshness, deterministic quant, strategy, and risk gates authoritative. No broker order placement is enabled by this integration.
- The NVIDIA NGC registry token used to pull a Docker image is not the hosted API Catalog key. Never use an NGC registry token as the API key. If a token was shared or committed, revoke and rotate it.


## Self-hosted NIM using the supplied Docker image

The backend already mounts `backend/app/kumo_nim_api.py` from `backend/app/main.py`; the router exposes `GET /v1/ai/kumo/status` and `POST /v1/ai/kumo/predict`. It supports either NVIDIA's hosted API Catalog or a separately hosted NIM container.

Run the supplied image only on a machine with a compatible NVIDIA GPU and the NVIDIA Container Toolkit:

```bash
docker login nvcr.io
# Username: $oauthtoken
# Enter your NGC API key at the password prompt; never put it in source control.
docker run -d --name kumo-tabular --restart unless-stopped \
  --gpus all --shm-size=16GB -p 8000:8000 \
  nvcr.io/nim/nvidia/kumo-tabular:1.0.0-rc2
```

Verify the NIM host locally before connecting Railway:

```bash
curl -fsS http://127.0.0.1:8000/v1/health/ready
```

**Important networking rule:** `http://127.0.0.1:8000` or `http://localhost:8000` on a developer's computer is not reachable from Railway. Expose the NIM host through a secure HTTPS endpoint/VPN or private network reachable by the backend, then set the base URL (without a trailing slash) in the Railway backend service variables:

- `KUMO_NIM_BASE_URL=https://<reachable-nim-host>`
- `KUMO_NIM_API_KEY=<optional gateway bearer token>` (only if the gateway requires it)

Keep the NIM endpoint access-controlled; do not expose an unauthenticated prediction service to the public internet. Do not put NGC or API Catalog credentials into the frontend or APK. If you prefer no GPU host management, use NVIDIA's hosted API Catalog and set `KUMO_NVIDIA_API_KEY` instead; do not configure both modes ambiguously.

### Call the backend proxy

The backend request shape wraps your supplied complete JSON envelope inside `request`. The example in the user-provided snippet is a customer-renewal classification demo, **not a trading model or market dataset**. Do not interpret its `renewed=yes/no` output as a market signal. For trading use, first define and validate a target from timestamp-aligned historical market data, include features that exist for prediction rows, and keep the Kumo result as external evidence until out-of-sample evaluation and deterministic risk validation pass.

```bash
curl -X POST 'https://<your-backend-host>/v1/ai/kumo/predict' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'X-Device-Id: <43-to-128-character-url-safe-device-id>' \
  --data-binary @- <<'JSON'
{
  "request": {
    "model": "kumo-tabular",
    "task": {},
    "schema": {},
    "context": {},
    "predict": {},
    "output": {"fields": ["prediction", "probabilities"]}
  }
}
JSON
```

Replace the abbreviated empty fields with the complete valid request envelope. For hosted API Catalog requests the backend validates the envelope and sends it to `https://ai.api.nvidia.com/v1/structured-data/nvidia/kumo-tabular/predictions`; for self-hosted NIM it sends the envelope to `KUMO_NIM_BASE_URL/v1/predictions`. A status/health response proves reachability only. A successful `/predict` response is the actual inference check. The response is evidence-only and never authorizes or places broker orders.
