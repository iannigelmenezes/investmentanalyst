# Known Issues & Gotchas

Read this before starting any work on the ECB Hawkometer.

---

## Scraper

- **ECB speech listing page is JS-rendered.** The URL `https://www.ecb.europa.eu/press/key/html/index.en.html` cannot be scraped with a plain HTTP GET — it requires JavaScript execution. The scraper uses the ECB foedb JSON API instead.
- **Many speeches are PDF-only.** The following speeches return binary PDF blobs, not readable HTML text. They are stored in the DB but `full_text` is empty/garbage:
  - Schnabel: Mar 27, Feb 18
  - Lane: Feb 9
  - Cipollone: Mar 21, Mar 6
  - Unknown speaker: Mar 25
  If new PDF-only speeches appear, they will show up with blank content in the dashboard.
- **`Unknown` speaker.** Some speeches in the foedb API have no attributed speaker. They are stored and scored under the name `"Unknown"` and appear in the dashboard board.

---

## Pipeline

- **Never run `ecb_hawkometer/main.py` directly.** It re-writes new-timestamp prompt files and then polls `data/results/` for result files that never arrive (because the polling loop and the inference step are in the same process). It will hang until timeout.
- **Always use `generate_dashboard.py`** to regenerate the dashboard. It reads the latest result JSON files directly and bypasses all polling.
- **The full pipeline run command is:**
  ```powershell
  $env:PYTHONIOENCODING="utf-8"; $env:TOKENIZERS_PARALLELISM="false"; & "C:\Users\MNZI\OneDrive - PGGM\Analyst\.venv\Scripts\python.exe" -W ignore "C:\Users\MNZI\OneDrive - PGGM\Analyst\generate_dashboard.py"
  ```
- **`generate_dashboard.py` auto-detects the latest batch** by picking the highest timestamp from `speaker_*.json` files in `data/results/`. To update the dashboard with new inference results, write new JSON files with a newer timestamp — the script will pick them up automatically.

---

## Data gaps

- **Sparklines are flat.** Per-speech hawkishness scores are not stored in the DB. The DB only stores metadata + embeddings. Sparklines use the aggregate speaker score repeated per speech, so they are a flat line. Fix requires adding per-speech score storage.
- **Policy prediction section not rendered.** `policy_20260402_093300.json` exists in `data/results/` but `generate_dashboard.py` does not pass it to `dashboard.generate_dashboard()` (`policy_prediction={}` is hardcoded). The dashboard UI section was removed during redesign.
- **12-week window only.** The scraper and DB cover the past 12 months but `generate_dashboard.py` loads only the last 13 weeks for sparkline data.

---

## Environment

- **PowerShell does not support `&&`.** Use `;` to chain commands, or use `if ($?) { ... }` for conditional chaining. Never write `cmd1 && cmd2` in PowerShell.
- **LSP import errors are false positives.** Errors like `Import "ecb_hawkometer.weights" could not be resolved` appear in the editor but do not affect runtime. The workspace uses runtime `sys.path` injection — the LSP does not see it.
- **pip must use trusted-host.** All pip installs must include:
  ```
  --trusted-host proget.pggm-intra.intern
  ```
  Without this, installs fail with `SSLCertVerificationError` on the PGGM internal PyPI.
- **Corporate CA cert** is at `C:\Users\MNZI\OneDrive - PGGM\Analyst\corporate_ca.pem`. The scraper uses it for HTTPS; falls back to `verify=False` with a warning if it fails.
- **Speaker name mismatch.** `weights.py` registers `"Philip Lane"` but inference results use `"Philip R. Lane"`. The weight lookup uses partial matching to handle this.
