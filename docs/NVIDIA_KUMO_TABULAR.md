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

- Kumo Tabular predicts classification labels or regression values from structured tables. It is not a general-purpose chat model and does not replace NVIDIA cloud chat or its OpenRouter fallback. Keep `KUMO_NVIDIA_API_KEY` dedicated to Kumo Tabular; configure `NVIDIA_API_KEY` separately for chat.
- A green status only indicates provider API reachability/authentication. Verify a real prediction before marking inference as working.
- Prediction output is not an approved trade. When `index` is supplied, the response includes `quant_connection` with the real model output attached as external evidence, the current deterministic gate verdict, and the unchanged Quant decision. This is deliberately not a trade-direction mapping: Kumo task/target semantics must be explicitly defined and validated before its label can participate in a decision. The bridge does not mutate the cached signal or override WAIT. Keep market-data freshness, deterministic quant, strategy, and risk gates authoritative. No broker order placement is enabled by this integration.
- The NVIDIA NGC registry token used to pull a Docker image is not the hosted API Catalog key. Never use an NGC registry token as the API key. If a token was shared or committed, revoke and rotate it.
