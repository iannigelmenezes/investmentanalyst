# Session Log

This file tracks what was done, what is broken, and what to do next across AI assistant sessions.
Update this file at the end of every session before closing the chat.

---

## Session 2026-04-23 (Session 4 — EUR swap curve investigation)

### What was done
- Diagnosed broken venv: base interpreter `C:\Programs\Anaconda3` no longer exists; venv shim was failing silently with "No Python at..." error
- Recreated `.venv` from system Python 3.13 (`C:\Users\MNZI\AppData\Local\Microsoft\WindowsApps\python.exe`)
- Reinstalled core packages into new venv: `requests`, `pandas`, `plotly`, `urllib3`, `python-dotenv`, `beautifulsoup4`, `lxml`, `pyyaml` (plus their deps)
- Investigated ECB SDW for EUR swap curve data:
  - Confirmed the ECB `YC` dataflow only covers the AAA euro area government bond curve (`G_N_A` instrument code)
  - Tested all plausible swap instrument codes (`S_S_0`, `IS`, `SI`, `SO`, `SE`) — all 404
  - Inspected `CL_INSTRUMENT_FM` codelist and `ECB_FMD2` DSD — confirmed no swap rate series in YC or FM dataflows
  - Conclusion: ECB does not publish EUR IRS swap rates via public API

### What is broken / incomplete
- `.venv` is now Python 3.13 (was 3.10); heavier packages not yet reinstalled: `torch`, `sentence-transformers`, `scikit-learn`, `transformers`, `huggingface-hub` — Hawkometer inference will fail until these are reinstalled
- `swap_30y_chart.py` and `tmp_dsd_check.py` are scratch files left in workspace root — can be deleted
- Policy prediction section still not rendered (carried over from Session 3)
- Sparklines still flat (carried over from Session 3)
- `Unknown` speaker still appears in board (carried over from Session 3)

### What to do next
- **Before any Hawkometer work**: reinstall `torch`, `sentence-transformers`, `scikit-learn` into the new venv
- **EUR swap data**: ECB is not a viable source. Options:
  - Bloomberg `blpapi` — `EUSW30 Curncy` (requires C++ SDK; PGGM has the licence)
  - ECB AAA 30Y government bond yield as a proxy (immediately available via existing `ecb_sdw.py`)
- See `BACKLOG.md` for other prioritised items

### Key decisions made
- Python invocation rule in `copilot-instructions.md` remains valid — the path `C:\Users\MNZI\OneDrive - PGGM\Analyst\.venv\Scripts\python.exe` now resolves correctly again
- EUR IRS swap rates are not available from ECB SDW — Bloomberg blpapi is the correct source at PGGM

---

## Session 2026-04-02 (Session 3 — context system overhaul)

### What was done
- Audited all context/documentation files in the workspace
- Created `SESSION_LOG.md` (this file) — persistent session memory
- Split `INVESTMENT_ANALYST_SPEC.md` into:
  - `SPEC_CORE.md` (270 lines) — fast-load every session: intent taxonomy, output templates, agent flow
  - `SPEC_PROVIDERS.md` (178 lines) — load on demand: provider registry, series IDs, bootstrap
  - Original `INVESTMENT_ANALYST_SPEC.md` kept with a header redirect note
- Rewrote `copilot-instructions.md` for OpenCode: correct Python invocation, required env vars, ECB Hawkometer rules, LSP false positive note
- Updated `features.json`: added `status: complete`, `build_complete_date`, `dashboard_ui_schema`, marked `tone_summary` and `representative_quote` as `deprecated_in_ui`
- Created `KNOWN_ISSUES.md` — scraper quirks, PDF speeches, pipeline gotchas, environment rules
- Created `BACKLOG.md` — prioritised feature candidates for Hawkometer and core analyst tool
- Updated `generate_dashboard.py` to write `ecb_hawkometer/data/results/CURRENT_BATCH.txt` after each run (batch timestamp + speaker count + last-week speech count)

### What is broken / incomplete
- Policy prediction section not rendered (same as Session 2)
- Sparklines still flat (same as Session 2)
- `Unknown` speaker still appears in board (same as Session 2)

### What to do next
- See `BACKLOG.md` — top candidate: re-introduce policy prediction section in chip/keyword UI style

### Key decisions made
- Context system restructured: `SPEC_CORE.md` is the primary fast-load file; `KNOWN_ISSUES.md` must be read before any Hawkometer work
- `CURRENT_BATCH.txt` is the canonical pointer to the active inference batch (avoids hardcoding timestamps)
- Active inference batch timestamp: `20260402_101453`

---

## Session 2026-04-02 (Session 2 — context continuation)

### What was done
- Rewrote `_build_speaker_board` in `ecb_hawkometer/dashboard.py`:
  - Added `_stance_badge()` helper function
  - Replaced `_theme_chips()` with `_keyword_chips()` (brighter colour for themes)
  - Added second chip row for `tone_keywords` (dimmer grey)
  - Added inline `stance_signal` badge next to speaker name
  - Renamed column header from "Key Themes" to "Themes / Tone"
- Rewrote `_build_deep_dive` in `ecb_hawkometer/dashboard.py`:
  - Removed `tone_summary` paragraph and `representative_quote` blockquote entirely
  - Added THEMES chip row (`key_themes`), TONE chip row (`tone_keywords`), STANCE badge (`stance_signal`)
  - Kept speech list and sparkline
- Regenerated dashboard successfully via `generate_dashboard.py`
- Audited all context files and applied improvements (SESSION_LOG, SPEC split, KNOWN_ISSUES, BACKLOG, CURRENT_BATCH, updated instructions)

### What is broken / incomplete
- Policy prediction section is not shown in the dashboard (intentionally removed during redesign; `policy_20260402_093300.json` exists but is not rendered)
- Sparklines are flat lines (per-speech scores not stored in DB; all speeches for a speaker share the same aggregate score)
- `Unknown` speaker appears in the board (speeches with no attributed speaker from the ECB foedb API)

### What to do next
- See BACKLOG.md for prioritised feature candidates
- Next likely session: re-introduce policy prediction section using keyword/chip style (consistent with new UI)

### Key decisions made
- Dropped `tone_summary` and `representative_quote` from UI — too verbose for a terminal-aesthetic dashboard
- `generate_dashboard.py` is the canonical entry point — never use `ecb_hawkometer/main.py` directly (times out on inference polling)
- File-based handoff pattern: Python writes prompt `.txt` files, OpenCode reads and writes `.json` result files, dashboard reads results
- Active inference batch timestamp: `20260402_101453`

---

## Session 2026-04-02 (Session 1 — initial build)

### What was done
- Built full ECB Hawkometer from scratch: F1–F6 scaffold, scraper, DB, analyzer, dashboard, router integration
- 52/52 tests passing
- Scraped 122 speeches, 26 in 8-week window, full text + embeddings stored
- Ran inference (timestamp `20260402_101453`): 7 speaker JSONs + 1 last-week JSON
- Redesigned "Speeches This Week" section: keyword chips, semantic tone comparison, ranking by speaker weight + policy relevance, shift badges, policy relevance dot bar, off-mandate dimming

### What is broken / incomplete
- `_build_speaker_board` and `_build_deep_dive` still used old paragraph/quote style (fixed in Session 2)

### Key decisions made
- ECB speech listing page is JS-rendered — use foedb JSON API instead
- Many speeches are PDF-only (Schnabel Mar 27, Feb 18; Lane Feb 9; Cipollone Mar 21, Mar 6; Unknown Mar 25) — stored as binary blobs, unreadable
- Speaker weights: Lagarde=1.0, Lane=1.0, Schnabel=0.8, de Guindos=0.8, Cipollone=0.8, Elderson=0.8, NCB governors=0.6, others=0.4
- `weights.py` uses "Philip Lane" but results use "Philip R. Lane" — partial match handles this
