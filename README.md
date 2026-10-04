# Covenant · Rental Housing Law Navigator · Team Deep State

Hack-Nation 7th Global AI Hackathon (Oct 3-4, 2026) · **Challenge 2, powered by RealPage**. _Not legal advice._

## Links
- **Live API** behind the app: https://covenant-api-ri6o.onrender.com/health (free plan: the first call after 15 idle minutes can take up to a minute)
- **Method note** (one page): [METHOD_NOTE.md](METHOD_NOTE.md)
- **Deliverables:** [outputs/rules.json](outputs/rules.json) · [outputs/lookups.json](outputs/lookups.json) · [outputs/changes.json](outputs/changes.json)

## What it does
For one building on one date, Covenant says **which rental rules apply** in six categories (rent increase limits, just-cause eviction, security deposits, application fees, screening restrictions, algorithmic rent-setting), **quotes the official text** for each, and answers **"unknown" plus the missing fact** when the records cannot decide. The app then orders the answer by who is reading: renter, landlord or public office.

Scope: 10 cities in California, New Jersey and Massachusetts · 500 sample addresses · change tests T1-T5. Plan and methodology: [PLAN.md](PLAN.md).

## How it works
```
starter/addresses ► enrich (Census: legal city, county, ZIP; units from use codes) ──► data/addresses_enriched.csv
starter/corpus ───► extract (LLM, every quote located verbatim in its source) ──────► outputs/rules.json
rules + addresses ► engine (deterministic: true/false/unknown, dates, precedence) ──► outputs/lookups.json
change tests ─────► changes (as-of runs before and after each test) ───────────────► outputs/changes.json
outputs ──────────► app_bundle ──► web app (same engine ported to TypeScript, EN/ES)
any address ──────► api (Census + public parcel records + the same engine, no LLM) ► web app
```
The model only reads the law. Plain code decides what applies, so every answer is reproducible and explainable.

## Results
| | |
|---|---|
| Rules | 88 (84 in force, 2 pending, 1 not yet effective, 1 failed), from 48 documents |
| Quotes | 88 of 88 found word for word in their source; a rule whose quote is not found is rejected |
| Addresses | 500 answered; 493 geocoded by the Census, 38 mailing cities corrected, unit counts known for 467 |
| Answers on Oct 1, 2026 | 8,541: 7,164 apply · 819 unknown · 220 pending · 198 superseded · 140 not yet effective |
| Change tests | T1 250 · T2 Hoboken 40 / Jersey City 50 / Newark 0 · T3 140 + 90 conflict flags · T4 110 pending · T5 recorded as failed, no Massachusetts rent cap |
| App engine vs pipeline | 0 mismatches over 34,166 answers (500 buildings, 4 dates), shown on the app's `/qa` page |

## What we built, step by step
| Step | File | Owner | What it does |
|---|---|---|---|
| 0 · Enrich addresses | `pipeline/enrich.py` | Ismail | 493/500 geocoded by the Census (4 via number ranges), 7 placed by postal city with county and city IDs inferred from the same city, 38 postal cities corrected, units known for 467/500 (257 supplied, 210 read from use codes), plus 1 supplied-vs-use-code conflict kept as a range, not guessed |
| 1 · Extract rules | `pipeline/extract.py` | Solal | The model fills the supplied rule schema; each quote is located in the source and replaced by the exact excerpt (rejected, retried once, if not found); duplicates merged; audit log in `outputs/extract_log.jsonl`; model answers cached, so a rerun costs nothing and gives the same result |
| 1b · Coverage linking | `pipeline/coverage_link.py` | Elie | A city's rent cap often comes from a rates page that never says which buildings are covered. The cap gets the program's building conditions from a sibling rule or a verbatim-checked sentence of the city's documents (SF 1979-06-13, LA 1978-10-01, Berkeley 1980, Santa Ana 1995), so it is not applied to new construction |
| 2 · Engine (address → laws) | `pipeline/engine.py` | Solal | Coverage in three-valued logic (true / false / unknown), status on the as-of date, precedence (local rent cap over state cap), per-address conflict flags; ambiguous years or disputed unit counts give "unknown" |
| 3 · Change tests T1-T5 | `pipeline/changes.py` | Solal | Runs the engine on all 500 addresses at each test's dates; affected addresses and conflict flags in `outputs/changes.json` |
| 4 · App data | `pipeline/app_bundle.py` | Solal | One data file for the app: rules, addresses, results at four dates, coverage, unknowns, changes, upcoming legislation ranked by certainty |
| Any address | `pipeline/online_address.py`, `pipeline/parcels.py`, `pipeline/answer.py` | Elie | Census geocoder plus the same public assessor dataset the sample used, for 9 cities; a parcel is accepted only if house number and street match; out-of-scope addresses are refused with a reason; every fact carries a "public data, not verified" warning |
| Live API | `pipeline/api.py`, `render.yaml` | Solal | Serves `answer()` to the app. Standard library only, no LLM, no key |
| Official texts | `pipeline/official_texts.py`, `pipeline/bill_texts.py` → `corpus_extra/` | Elie | 11 official texts fetched one page at a time from government sites (no crawling), each with its source URL and retrieval time |
| Legislation monitor | `pipeline/legislation.py`, `pipeline/council.py` | Elie | 34 state bills (LegiScan, latest action cross-checked with Open States), Boston and Newark council items (Legistar). Shown only under "Coming up", marked "not reviewed", never an input to the deliverables |
| Web app | Lovable (React, TypeScript) | Solal | Address report with quoted evidence and a link to the official text, guided questions for missing facts, as-of date, portfolio, changes, coverage, legislation radar, English and Spanish |

## Checks
- **Quotes:** `python -m pipeline.extract --verify-only` re-checks every quote against its source, without the model.
- **Change tests:** `make changes` prints the T1-T5 results and its own assertions.
- **App entry point:** `make answer-check` runs 7 self-tests and checks that nothing from outside the supplied data is shown without its warning.
- **Live address lookup:** `make online-check` compares the public lookup with the supplied sample.
- **App engine:** the `/qa` page of the app compares the TypeScript engine with the pipeline's results on every answer.
- We did not build a hand-labeled gold set, and no lawyer reviewed the output.

## Sources outside the starter pack
33 of the 87 supplied documents are links without text. We added 11 official texts (Jersey City, Hoboken and Newark ordinances, the Massachusetts court ruling, San Diego's enacted code). 14 of the 88 rules come from them; they carry `provenance` other than `starter` in `rules.json` and a warning in the app. T2, T3 and T5 depend on them. `make extract` without `SOURCES=all` rebuilds `rules.json` from the supplied corpus only.

## Run it
```bash
make setup                 # Python venv + dependencies
cp .env.example .env       # add your API key, never commit .env
make all SOURCES=all       # enrich -> extract -> engine -> changes: rebuilds the submitted outputs
                           # (model answers are cached in data/cache/llm/, so this costs nothing)
make ingest DOC=X001,X002  # add new law texts from corpus_extra/ end to end
make external              # bills, council items, enacted bill texts
make online ADDR="300 Summit Ave, Jersey City, NJ"   # an address outside the 500 (public parcel data)
.venv/bin/python -m pipeline.api                     # the live API, on port 8000
```
One address: `.venv/bin/python -m pipeline.engine --address A0016 --as-of 2026-10-01`
What the app shows for any address, with warnings: `.venv/bin/python -m pipeline.answer "50 Bowdoin St, Boston, MA"`

## Repo layout
```
starter/       RealPage starter pack (corpus, addresses, schema, tests). Never edited
corpus_extra/  official texts we added, with a manifest (source URL, retrieval time, provenance)
pipeline/      our code, one file per step
data/          addresses_enriched.csv, caches (Census, model answers), external data
outputs/       rules.json, lookups.json, changes.json (the deliverables), extract_log.jsonl, app/ (app data)
PLAN.md        plan, methodology, lanes, timeline, data contracts
METHOD_NOTE.md one-page method note
```

## Team
| Name | Lane | GitHub |
|---|---|---|
| Solal Abitbol | Rule extraction, engine, change tests, web app | @solal24 |
| Ismail Ameur | Address data: geocoding, legal city, unit counts | @IsmaA24 |
| Elie Abou-Fadel | External data: official texts, live address lookup, legislation monitor, coverage linking | @eaboufadel3 |
