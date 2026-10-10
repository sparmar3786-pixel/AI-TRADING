# FinGPT vendor import notes

- Upstream: https://github.com/AI4Finance-Foundation/FinGPT
- Branch: `master`
- License: MIT; upstream license retained at `vendor/FinGPT/LICENSE`.
- Source fetched on 2026-10-10/11.
- Imported the ForexIntelligence module and selected FinGPT Forecaster application, market-data pipeline, sentiment/symbol configuration, prompt, training and deployment files under `vendor/FinGPT/FinGPT_Forecaster/`.
- This remains a partial import, not the complete FinGPT repository. Notebooks, datasets, model weights, benchmark tasks and many other source files are not copied. Some existing files were already present and retained rather than overwritten.
- Dependencies are recorded in the imported requirements files; they have not been installed or tested in this pass.
- Upstream package source may require additional files/configuration and should not be considered production-ready without tests.
