# PLAN · Team Deep State · Rental Housing Law Navigator (RealPage, Challenge 2)

> Read this before every decision. Source of truth for scope, lanes and timing. Brief: `starter/mit-rental-housing-law-navigator-challenge-v5-...pdf` + `starter/README.md` (participant guide).

## North star
For any address and any date: which of the 6 rule categories apply, with an **exact, verified citation**, and **"unknown" + the missing fact** when the data can't say. Then answer the user's **intent** (renter / landlord / legislator / public office), not just list laws.

**Scope fence:** 3 states · 10 cities · 6 categories · 500 sample addresses · tests T1-T5.
**Deadline:** Sun Oct 4, 9:00 AM ET. **We submit at 8:30.**

## What the judges expect (v5)
- `rules.json`, `lookups.json` (all 500, as_of 2026-10-01), `changes.json` (T1-T5), **live demo**, **one-page method note**. Confirm with organizers: videos? score.py / dev key? JC/Hoboken ordinance text?
- Strong = every answer shows source doc, quoted span, retrieval date, as-of date · enacted / pending / not-yet-effective / failed separated · "unknown" instead of guessing · conflicts flagged for human review · audit log, reproducible.
- Must not: legal advice, invented rules/citations, non-public data, scraping against site terms. **"Not legal advice" on every screen.**

## Architecture: the LLM extracts, code decides
```
starter/corpus/text ─► 1 EXTRACT (Claude, structured output) ─► span verifier ─► outputs/rules.json
sample_addresses.csv ─► 0 ENRICH (Census geocoder: legal city, county, ZIP, GEOIDs; use-code → unit bounds) ─► data/addresses_enriched.csv
rules + addresses ────► 2 ENGINE (deterministic, true/false/unknown, dates, precedence, conflicts) ─► outputs/coverage.json, outputs/lookups.json
change_tests.json ────► 3 CHANGES (as-of runs T1-T5) ─► outputs/changes.json
all of the above ─────► 4 EVAL + AUDIT (gold set, span check, schema, T1-T5 asserts, runs/<ts>/ log)
outputs → Supabase ───► 5 APP (Lovable): role → address → verdict + sources, EN/ES (FR bonus), "not legal advice"
```
`make all` reproduces everything. `make ingest DOC=path` adds one new document end to end (demo moment).

### Non-negotiable rules
1. **Every `quoted_span` is verified verbatim** (whitespace-normalized) in its source doc, or the rule is rejected and re-extracted.
2. **Never hand-edit `rules.json`.** Fix prompts/code. (Hand-labeling the *gold eval set* is fine.)
3. **Deliverables use only supplied data** (+ geocoding). Any enrichment (public parcel data, user-entered facts, monitoring) lives in a separate layer, labeled with its provenance: `supplied` / `public` / `user`.
4. **LLM proposes, human approves.** New/changed laws from monitoring go to a review queue, never straight into the rule table.
5. **No merge to `main` if `make eval` gets worse.**

## Lanes (one owner each, swap names if you want)
| Lane | Owns |
|---|---|
| **A · Extraction** | `pipeline/extract.py`, prompts, span verifier, `rules.json`, supplemental docs (`starter/corpus/supplemental/`, only if organizers OK) |
| **B · Engine** | `pipeline/enrich.py` (geocode + use codes), `pipeline/engine.py`, `pipeline/changes.py`, `lookups.json`, `changes.json` |
| **C · Eval + Product + Story** | `eval/` (gold set, checks), audit log, Lovable app, method note, demo, videos, organizer contact |

## Priorities (do them in order)
**P0 · scored core:** enrich → extract + verified citations → engine → 3 JSONs → our eval.
**P1 · intent-based app:** role picker → address search → verdict + what applies + what's unknown (missing fact) + what's coming + sources + as-of date · EN/ES.
**P2 · differentiators:** "What would flip this answer?" (counterfactual missing fact) · answer receipt (hash of source + span + rule + engine version) · impact map (500 buildings by regime, city limits) · known-unknowns register (the 4 open questions in guide §9).
**P3 · bonus (only after 05:00 if all green... or never):** policy simulator for legislators · monitoring (LegiScan / Open States / Legistar + manifest sha256) · voice chatbot (ElevenLabs, grounded on our rules only) · FR · addresses outside the sample.

### Intent by role (P1)
| Role | Their question | What we show |
|---|---|---|
| Renter | Is my increase / deposit / fee legal? | Calculator: current rent + proposed → "max allowed $X", rights (eviction, fees), source |
| Landlord | Can I do this before acting? | Checklist: max increase, max deposit, fees, algorithmic pricing allowed?, upcoming changes |
| Legislator | What does this bill change, for whom? | Bill → # buildings affected, map, conflicts with existing law |
| Public office | Who is protected where, where are gaps? | Coverage by city, unknowns to resolve, open questions |
Output template for every role: **Verdict → What applies → What we don't know (and which fact) → What's coming → Sources (span, retrieved, as-of) → Not legal advice.**

## Timeline (ET)
| Time | Goal | Done when |
|---|---|---|
| 16:00-16:30 | Align on this plan, contracts (appendix below), lanes. Send organizer question. Keys in `.env`. Create Lovable project. | Everyone runs `make enrich` locally |
| 16:30-19:30 | **v1 in parallel.** A: extraction v1 on 54 docs + verifier. B: enrichment done, engine skeleton. C: gold set (~15 rules, ~30 addresses hitting every trap) + `make eval`, Lovable shell on template JSON. | rules.json v1, addresses_enriched.csv, eval report |
| 19:30 | **Checkpoint 1** (15 min) | Top 5 errors assigned |
| 19:30-23:30 | **End to end.** Engine → lookups + changes. Extraction v2 from eval errors. App on real data (role → address → verdict). | `make all` from scratch, 3 JSONs valid |
| 23:30 | **Checkpoint 2** | T1-T5 asserts pass, app shows real answers |
| 23:30-03:00 | Quality loop every 45 min · P2 differentiators · deploy live link · EN/ES | Outsider can use the live link |
| 01:00-05:00 | Sleep 90 min each, staggered | |
| 03:00 | **Checkpoint 3**: freeze "v1 results" metrics | |
| 03:00-05:00 | P3 only if P0-P2 green | |
| **05:00** | **FEATURE FREEZE** | |
| 05:00-07:30 | Method note, README, clean-clone `make all`, videos if required, screenshots | Clean clone reproduces JSONs |
| 07:30-08:30 | **Submit** | Confirmation |

## Demo script (2 min)
1. Pick **Renter**, type a **Dorchester** address → resolved to Boston → deposit cap applies (G.L. c.186 §15B, quoted, retrieved date) · **no rent cap** (c.40P, ballot question failed) · MA algorithmic bills **pending**.
2. SF 1962 building → SF Rent Ordinance, AB 1482 **superseded**; 1979 building → **unknown** + "What would flip this: certificate of occupancy on or before 6/13/1979".
3. Switch to **Landlord** in Jersey City, as-of 2027-07-02 → FAIR Act applies + **conflict flag** with the local ban.
4. **Legislator**: MA S.2983 → N buildings affected, map.
5. Audit view / answer receipt → `make ingest` a new ordinance live.
6. Close: our eval numbers + moonshot (every US jurisdiction as verified rules-as-code; compliance for property managers, rights for renters).

## Anti-drift
- Every checkpoint: "Does this move the north star or a deliverable?" If not → parking lot at the end of this file.
- Stuck > 30 min → say it in the group, pair up.
- Data completion is time-boxed: **2h max** total.

## Appendix · Data contracts

## Tables (Supabase / CSV / JSON)
```
documents     (doc_id PK, jurisdictions, url, source_type, retrieved_at, sha256, text_file, provenance)
jurisdictions (jurisdiction_id PK, name, level: state|county|city, parent_id FK, geoid)
addresses     (address_id PK, street_address, postal_city, state, zip, year_built, units, use_code,
               use_description, source_dataset,
               legal_city, legal_city_geoid, county, county_geoid, state_geoid, zip_geocoded, lat, lon,
               geocode_match, units_min, units_max, units_source, provenance)
rules         (rule record per starter/schema/rule_record.schema.json, coverage_conditions = object below)
lookups       (address_id FK, team_rule_id FK, as_of, result, explanation, missing_facts[], conflict_flag)
```
Jurisdiction keys: state = `CA|NJ|MA`; city = `"<City>, <ST>"` exactly as in the schema (e.g. `"San Francisco, CA"`). **Never join on ZIP or postal_city.**

## Rule record
Exactly `starter/schema/rule_record.schema.json`, plus this structure for `coverage_conditions` (the engine reads it; null field = no condition):
```json
{
  "built_before": "1979-06-13",          // year built / CO strictly before (or on, see next)
  "built_cutoff_uses_co_date": true,     // true → a building built in the cutoff year is "unknown"
  "built_after": null,                   // e.g. new-construction exemptions (built within last 15 years)
  "min_units": 2, "max_units": null,
  "excludes_owner_occupied_min_units": null,  // e.g. owner-occupied <= 2 units exempt → owner type unknown
  "excludes_single_family": true,
  "building_types": null,                // e.g. ["multifamily"]
  "facts_required": ["year_built","units"],   // facts the engine must have
  "notes": "free text from the law"
}
```
Rule `status` is as of 2026-10-01; the engine recomputes for other dates from `effective_date`.

## Engine result per (address, rule)
`applies | unknown | superseded | not_yet_effective | pending` (rules that don't apply are omitted).
- Missing fact → `unknown`, and `missing_facts` names it (e.g. `["year_built"]`).
- `explanation` is one plain sentence a renter can read.
- Precedence: when a local rule governs the same category more strictly, the state rule is `superseded`.

## Address enrichment
- `units_min/units_max` from `units` if present, else parsed from `use_code/use_description` (e.g. SF `A5` → 5-14, NJ `6B-20U-G` → 20), `units_source` = `supplied|use_code`.
- `provenance` = `supplied` for the 500. Anything else (public parcel data, user input) = `public|user`, never mixed into the deliverables.

## Parking lot (good ideas, not now)
- 
