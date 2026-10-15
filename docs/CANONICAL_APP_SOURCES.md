# Canonical application sources

This repository currently has two distinct application targets. Do not treat them as interchangeable.

## Web application
- Canonical branch: `main`
- Source: `src/`
- Web CI: repository workflows that build/test the React/Vite application from `main`
- The web deployment must build from `main` (or a reviewed commit descended from it).

## Android / Flutter APK
- Canonical source branch: `feat/ai-trading-signal-apk`
- Flutter project root: `flutter_app/`
- Android build workflow: `.github/workflows/android-apk.yml`
- Flutter source validation workflow: `.github/workflows/flutter-source-check.yml`
- The APK must be built from the exact reviewed commit on this branch. Record that commit SHA with every release artifact.
- Do not copy `src/` web pages into Flutter or restore old APK pages from `main`. Web and Flutter navigation are separate implementations.

## Removed APK pages
The Flutter navigation must not contain `AI Chat` or `PDF Reports`; their Flutter page files were removed in the APK branch. Widget tests assert those tabs remain absent.

## Release gates
1. Run `flutter pub get`, `flutter analyze`, and `flutter test` from `flutter_app/`.
2. Run the Android APK workflow only after those checks pass.
3. Verify the artifact commit SHA matches the reviewed branch commit and inspect the APK navigation before distribution.
4. Web green CI does not prove Flutter/APK correctness, and Flutter CI does not prove the web deployment is correct.
5. Provider status must be based on a real successful inference; configuration-only diagnostics are not proof that NVIDIA or OpenRouter is actively responding.
6. Never present cached, synthetic, or fallback market data as live. Actionable signals require fresh trusted-source data and passing deterministic validation.
7. Firebase/Firestore deployment and broker integration require separate authenticated ownership/security tests; source rules alone do not prove deployed rules are active.
