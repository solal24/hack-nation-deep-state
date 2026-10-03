# Rental Housing Law Navigator · Team Deep State

Hack-Nation 7th Global AI Hackathon (Oct 3-4, 2026) · **Challenge 2, powered by RealPage**.
**Submission deadline: Sun Oct 4, 9:00 AM ET.** _Not legal advice._

## What it does
For any apartment address and any date, it answers **which housing rules apply** (rent increase limits, just-cause eviction, security deposits, application fees, screening restrictions, algorithmic rent-setting), **with an exact, verified citation**, and says **"unknown" plus the missing fact** when the data can't decide. Then it answers the user's **intent** depending on who they are: renter, landlord, legislator or public office.

Scope: 3 states (CA, NJ, MA) · 10 cities · 500 sample addresses · change tests T1-T5. Full plan and methodology: [PLAN.md](PLAN.md).

## How it works
```
starter/corpus ──► extract (LLM, quotes verified verbatim) ──► outputs/rules.json
starter/addresses ► enrich (Census: legal city, county, ZIP; units from use codes) ──► data/addresses_enriched.csv
rules + addresses ► engine (deterministic: true/false/unknown, dates, precedence) ──► outputs/lookups.json
change tests ─────► changes (as-of runs) ──► outputs/changes.json
outputs ──────────► Lovable app (role → address → verdict + sources, EN/ES)
```
The LLM only reads the law; plain code decides what applies, so every answer is reproducible and explainable.

## Status
| Step | File | Owner | Status |
|---|---|---|---|
| 0 · Enrich addresses | `pipeline/enrich.py` | Ismail | ✅ 489/500 geocoded by Census, 38 postal cities corrected, units known for 468/500 |
| 1 · Extract rules | `pipeline/extract.py` | Solal | 🟡 branch `feat/extract-rules`: 75 rules from 54 docs, 75/75 quotes verbatim; reads `corpus_extra/` too. Gaps: Hoboken, Newark, JC algorithmic ban, MA ballot question (texts from Elie) |
| 2 · Engine (address → laws) | `pipeline/engine.py` | Solal | 🟡 branch `feat/extract-rules`: `outputs/lookups.json` for all 500 on real rules; precedence (local rent cap > state cap), per-address conflicts, ambiguous years → unknown; any address via `--free` |
| 3 · Change tests T1-T5 | `pipeline/changes.py` | Solal | 🟡 `outputs/changes.json`: T1 ✅ 250, T3 ✅ dates (conflicts wait for JC/Hoboken texts), T4 ✅ 110, T5 ✅ empty; T2 waits for JC/Hoboken texts |
| 4 · Evaluation | `eval/` | _tbd_ | ⏳ |
| External data · addresses outside the sample | `pipeline/online_address.py`, `pipeline/parcels.py` → `data/addresses_online.csv` | Elie | 🟡 on branch `feat/external-data`: Census + same assessor source as the sample for all 9 cities; reproduces 89/89 sample facts (`make online-check`); `provenance=public` + warning, never in the deliverables |
| External data · legislation monitor | `pipeline/legislation.py`, `pipeline/council.py`, `pipeline/bill_texts.py` → `data/external/` | Elie | 🟡 on branch `feat/external-data` (`make external`): 34 CA/NJ/MA housing bills (LegiScan, cross-checked 34/34 with Open States, all 6 change-test bills tracked), Boston + Newark council items (Legistar; other cities have no public feed), official texts of 5 enacted bills + verbatim effective-date clause (FAIR Act → 2027-07-01). `watchlist.json` = "What's coming" per state/city. All `provenance=public`, unreviewed, never in the deliverables |
| App | Lovable | _tbd_ | ⏳ |

## Run it
```bash
make setup      # Python venv + dependencies
cp .env.example .env   # add your API key, never commit .env
make enrich     # step 0
make extract    # step 1 (LLM via Claude Code login in ~/.claude-enterprise; answers cached in data/cache/llm/)
make engine     # step 2 -> outputs/lookups.json
make changes    # step 3 -> outputs/changes.json
make ingest DOC=X001,X002   # add new law texts from corpus_extra/ end to end
make extract SOURCES=starter   # official rules.json from the RealPage corpus only
```
One address: `.venv/bin/python -m pipeline.engine --address A0016 --as-of 2026-10-01`

## Repo layout
```
starter/    RealPage starter pack (corpus, addresses, schema, tests). Never edited
pipeline/   our code, one file per step (+ llm.py, dev_rules.json for engine testing only)
eval/       our gold set and checks
data/       addresses_enriched.csv (+ Census cache)
outputs/    rules.json, lookups.json, changes.json (the deliverables)
PLAN.md     plan, methodology, lanes, timeline, data contracts
```

## Team
| Name | Role | GitHub |
|---|---|---|
| Solal Abitbol | Address → laws (engine) | @solal24 |
| Ismail Ameur | Data processing | @IsmaA24 |
| Elie Abou-Fadel | External data | @eaboufadel3 |

## Working together
- `git pull` before you start, one branch per feature (`feat/<name>`), merge to `main` only when it runs
- **Update the Status table in this README whenever a step changes**
- Never commit API keys (`.env` only), never hand-edit `outputs/rules.json`

## Submission checklist
- [ ] `outputs/rules.json`, `outputs/lookups.json` (all 500), `outputs/changes.json` (T1-T5)
- [ ] Live demo link, "Not legal advice" on every screen
- [ ] One-page method note
- [ ] Videos if required by Hack-Nation (confirm)
- [ ] Submitted before 9:00 AM ET (target 8:30)
