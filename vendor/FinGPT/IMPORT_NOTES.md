# FinGPT vendor import notes

- Upstream: https://github.com/AI4Finance-Foundation/FinGPT
- Branch: `master`
- License: MIT; upstream license retained at `vendor/FinGPT/LICENSE`.
- Source fetched on 2026-10-10.
- Imported the ForexIntelligence module files and selected forecasting prompt/sentiment/symbol modules into this directory.
- This is a partial import, not the complete FinGPT repository. Model weights, datasets, notebooks, and many other source files are not copied.
- Dependencies are listed in the imported ForexIntelligence requirements file; not installed or tested here.
- Upstream package source may require additional files/configuration and should not be considered production-ready without tests.
