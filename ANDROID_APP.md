# AI-TRADING Android signal app

The Flutter app in flutter_app is based on the user's existing Fresh-Apk UI and is adapted for the AI-TRADING repository. It calls the existing Railway HTTPS API:

https://nse-algo-backend-final-production.up.railway.app

## Signal-only safeguards

- The app has no order-submission method or button; it cannot place, modify, or cancel broker orders.
- A CALL BUY / PUT BUY candidate must pass backend validation and keep the same side and strike for 10 continuous minutes before the UI exposes it as actionable.
- A candidate change, failed validation, or gap longer than 60 seconds between successful app refreshes resets the stability window.
- Cached data is display-only. If the live API request fails, actionable signals are changed to WAIT and cross-index trade plans are cleared.
- The ten-minute stability gate is a confirmation filter, not a guarantee that a trade will remain profitable or should be held for ten minutes. Verify quote freshness, spread, liquidity, slippage, and risk.

## Angel One credentials

Keep API key, client code, MPIN/PIN, TOTP seed, JWT, refresh token, and feed token in Railway/server-side secret configuration only. Never put them in Dart constants, APK build arguments, repository files, or GitHub Actions logs. This APK uses authenticated backend endpoints and does not authenticate directly to Angel One.

## Build and distribution

The workflow bootstraps Android project files, sets Android minSdk to 26 (required by llama_flutter_android), runs Dart analysis and Flutter tests, builds a universal release APK for broad Android ABI compatibility, verifies the Railway host and internet permission, and publishes one rolling prerelease asset at GitHub Releases. Android 8.0 (API 26) or newer is required. It deliberately avoids upload-artifact because the existing Fresh-Apk Actions artifact quota had been exhausted.

The app is not a guarantee of returns. Live Angel One session health, market data freshness, option-chain completeness, and on-device behavior still require separate verification. The repository's Python engine and vendored research code are not automatically invoked by this Flutter app unless a deployed backend explicitly integrates them.
