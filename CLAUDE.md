# CLAUDE.md · Team Deep State

Shared context for every teammate's Claude. Keep it short and up to date.

## Event
Hack-Nation 7th Global AI Hackathon. 24h build. **Submission deadline: Sun Oct 4, 9:00 AM ET (hard).**
Judges value a working demo above everything: a polished narrow feature beats a broken ambitious one.

## Challenge
**Challenge 2 · Rental Housing Law Navigator (RealPage).** Starter pack in `starter/` (read `starter/README.md`). Deliverables: `outputs/rules.json`, `outputs/lookups.json`, `outputs/changes.json`, live demo, one-page method note.

## Our idea
**Read `PLAN.md` first** (north star, lanes, priorities, timeline) (appendix: data contracts). LLM extracts rules with verified quotes; deterministic code decides coverage; intent-based app per role (renter / landlord / legislator / public office).

## Team and ownership
| Person | GitHub | Owns |
|--------|--------|------|
| Solal | solal24 | **Address → laws**: jurisdiction stack, rule matching, coverage logic, results (`pipeline/engine.py`), branch `feat/address-lookup` |
| Elie Abou-Fadel | eaboufadel3 | **External data**: missing law texts (link-only docs), legislative APIs, public parcel data. Respect site terms, no bulk scraping |
| Ismail Ameur | IsmaA24 | **Data processing**: addresses (`pipeline/enrich.py`), corpus cleaning, tables per the data contracts in PLAN.md |

Only edit files owned by your human unless they ask otherwise. If you must touch shared files (`pipeline/llm.py`, `requirements.txt`, `PLAN.md`, this file), keep the change minimal and mention it in the commit message.

## Partners (use them, judges notice)
- **Lovable**: AI app builder (React + Supabase). Use it for the user-facing app
- **Wajo AI / Fo**: agent that books, buys, pays, calls, emails. Use it for the real-world action in the demo
- **ElevenLabs** (credits + own challenge, TBD): voice, TTS, voice agents that can place phone calls via API
- **Bright Data** (credits): web scraping / unblocking / SERP API / ready-made scrapers. Use it to get real data instead of synthetic

## Stack
- Repo layout: `starter/` (given by RealPage, never edit) · `pipeline/` (our code, one file per step) · `eval/` (gold set + checks) · `data/` (enriched addresses + Census cache) · `outputs/` (the 3 deliverable JSONs)
- Run steps with `make enrich|extract|engine|changes|eval|all` (Python venv: `make setup`)
- LLM calls go through `pipeline/llm.py` (`ask`, `ask_json`). Model set by `CLAUDE_MODEL` in `.env`
- Frontend: Lovable app (its own synced repo, link it here once created). The app gets everything for one address from `pipeline.answer.answer(address, as_of)`: never show a verdict, bill or address fact without the `warnings` it comes with (anything not from the supplied data carries one; `check_warnings` enforces it)
- Keys live in `.env` only (copy `.env.example`). Never commit `.env`, never hardcode keys

## How to hand data to the pipeline
- New law texts (Elie): never edit `starter/`. Save each text as `corpus_extra/text/X001.txt` starting with `SOURCE: <url>` and `RETRIEVED: <YYYY-MM-DD HH:MM UTC>`, full text below, no summary, no rewriting. Add one row to `corpus_extra/manifest.csv` (same columns as `starter/corpus/corpus_manifest.csv` + `provenance`: `elie_manual` | `legiscan_api` | `openstates_api`). Bills: keep the official bill text and note status + dates in the row. Then run `make ingest DOC=X001`.
- Never write rules by hand: rules only come from `pipeline/extract.py` (LLM extraction + verbatim quote check). Rules from `corpus_extra/` are flagged "to review" and kept out of the official deliverable unless organizers allow them.
- Addresses (Ismail): `data/addresses_enriched.csv` is the engine's input. Keep the existing column names (`legal_city`, `year_built`, `units_min`, `units_max`...). Add columns, never rename or remove.
- Fetch pages one by one, respect site terms, no bulk scraping (ecode360, American Legal, Justia).
- Work in progress: engine on branch `feat/address-lookup`, extraction on `feat/extract-rules` (Solal).

## Rules for Claude
- Never hand-edit `outputs/rules.json`; extraction must be automated. Every `quoted_span` must exist verbatim in its source doc
- Deliverables use only supplied data (+ Census geocoding). Enrichment is a separate, provenance-labeled layer
- Never join on ZIP or postal_city; use the geocoded legal city
- Don't create new top-level folders; ask the team first
- When a step changes status, update the Status table in README.md in the same commit; new decisions go in PLAN.md
- `main` must always run. Work on a branch `feat/<name>`, merge only when it runs
- Always `git pull` before starting work; commit small, push often
- Prefer the simplest thing that demos well. No premature abstractions, no test suites unless asked
- Before the deadline, priority order: demo works > README explains it > code is clean
- Update the "Challenge", "Our idea" and "Team" sections when the team decides
