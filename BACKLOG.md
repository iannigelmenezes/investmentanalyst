# Backlog

Candidate features in rough priority order. Move items to SESSION_LOG.md when work starts.

---

## ECB Hawkometer

### High priority
- **Re-introduce policy prediction section** — `policy_*.json` result files already exist and have the right schema. Redesign the section using keyword/chip UI style (consistent with speaker board). Currently `generate_dashboard.py` passes `policy_prediction={}` so nothing renders.
- **Per-speech hawkishness scores** — store a score per speech in the DB (new column). This unblocks real sparklines (currently flat). Requires updating `analyzer.py` prompt schema and `db.py`.
- **Alert / diff mode** — compare current batch vs prior batch; flag speakers whose score shifted >1.5 points. Output as a summary row at the top of the dashboard or as a separate alert card.

### Medium priority
- **PDF speech extraction** — for PDF-only speeches (Schnabel, Lane, Cipollone, others), attempt text extraction via `pdfminer` or `pymupdf`. Fall back gracefully if extraction fails.
- **Historical batch comparison** — `generate_dashboard.py` currently only renders the latest batch. Add a simple trend chart showing how each speaker's score has moved across batches over time.
- **Tone shift heatmap** — a compact grid (speakers × weeks) showing score by colour, replacing or supplementing the sparkline.

### Low priority / exploratory
- **Expand to Fed speakers (FOMC Hawkometer)** — same architecture, different scraper target (Fed website speeches). Reuse all inference and dashboard infrastructure.
- **Bloomberg integration** — overlay ECB OIS curve or ESTR forwards on the dashboard to contextualise hawkishness scores against market pricing.
- **Automated inference trigger** — instead of manual file-based handoff, trigger Claude inference via API when new prompt files appear (requires API key and network access to Anthropic endpoint).
- **Email/Teams digest** — on each dashboard regeneration, send a short summary (top movers, this week's speeches) to a configured recipient.

---

## Core Analyst Tool

### Medium priority
- **`ISSUANCE` intent** — currently a stub. No standard API covers all EU DMO issuance plans. Build a scraper for Bundesfinanzagentur, AFT, DSTA websites, or use ECB SDW historical issuance series as a proxy.
- **`FLOW_MAP` intent** — Sankey diagram for energy flows. Eurostat `nrg_ti_gas` and `nrg_ti_oil` datasets are registered in `providers.yaml` but the intent handler is not fully implemented.
- **Improve intent classifier** — `router.py` uses simple keyword counting. A short embedding-based classifier would handle ambiguous queries better (e.g. "what is ECB likely to do" currently maps to unknown).

### Low priority
- **Query history** — log every query + intent + result to a local SQLite DB for audit/replay.
- **Multi-chart output** — some intents (CROSS_SECTION, RATES_CURVE) would benefit from 2-panel charts. Currently each intent generates a single `output.html`.
