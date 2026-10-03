# Data contracts (shared by lanes A, B, C · change only after telling the group)

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
