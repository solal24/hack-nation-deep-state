"""Step 4 · Compact data bundle for the web app (no server, no LLM at runtime).

Writes outputs/app/navigator_data.json:
  rules      -> the fields the UI shows (plain rule, key value, citation, source, quote, retrieval date...)
  addresses  -> the 500 sample buildings (legal city, facts, where each fact comes from)
  results    -> engine output per address for a few as-of dates (rule id, result, missing facts, conflict)
  coverage   -> 13 jurisdictions x 6 categories matrix (rule / pending / not yet effective / none)
  unknowns   -> why answers are "unknown" (missing fact x city), for the public-office view
  changes    -> T1-T5 summaries
Run: python -m pipeline.app_bundle
"""
import collections
import json

from pipeline.engine import DISCLAIMER, ROOT, facts_from_row, load_addresses, load_rules, lookup

AS_OF_DATES = ["2025-12-31", "2026-01-02", "2026-10-01", "2027-07-02"]
CATEGORIES = ["rent_increase_limits", "just_cause_eviction", "security_deposits",
              "application_screening_fees", "screening_restrictions", "algorithmic_rent_setting"]
JURISDICTIONS = ["CA", "Los Angeles, CA", "San Francisco, CA", "San Diego, CA", "Berkeley, CA", "Santa Ana, CA",
                 "NJ", "Jersey City, NJ", "Hoboken, NJ", "Newark, NJ", "MA", "Boston, MA", "Cambridge, MA"]
RULE_FIELDS = ["team_rule_id", "jurisdiction", "level", "category", "status", "title", "requirement", "key_value",
               "coverage_conditions", "exemptions", "effective_date", "citation", "source_doc_id", "source_url",
               "retrieved_at", "quoted_span", "confidence", "conflict_note", "provenance", "review_status"]


def main():
    rules = load_rules()
    addresses = load_addresses()
    out_rules = [{k: r.get(k) for k in RULE_FIELDS} for r in rules]

    out_addr = []
    for aid, row in addresses.items():
        f = facts_from_row(row)
        out_addr.append({
            "id": aid, "street": row["street_address"], "postal_city": row["postal_city"], "state": row["state"],
            "zip": row.get("zip_geocoded") or row["zip"], "legal_city": row["legal_city"],
            "legal_city_source": row.get("legal_city_source"), "year_built": f["year_built"],
            "units_min": f["units_min"], "units_max": f["units_max"], "units_source": row.get("units_source"),
            "use_description": row["use_description"], "lat": row.get("lat"), "lon": row.get("lon"),
        })

    results = {}
    for d in AS_OF_DATES:
        results[d] = {aid: [[r["team_rule_id"], r["result"], r["missing_facts"], r["conflict_flag"]]
                            for r in lookup(row, rules, d)] for aid, row in addresses.items()}

    cov = {j: {c: [] for c in CATEGORIES} for j in JURISDICTIONS}
    for r in rules:
        if r["jurisdiction"] in cov and r["category"] in CATEGORIES:
            cov[r["jurisdiction"]][r["category"]].append({"id": r["team_rule_id"], "status": r["status"]})

    unknowns = collections.Counter()
    for aid, rows in results["2026-10-01"].items():
        for _, res, missing, _ in rows:
            if res == "unknown":
                for m in missing or ["other"]:
                    unknowns[(addresses[aid]["legal_city"], m)] += 1
    unknown_rows = [{"city": c, "missing_fact": m, "answers": n} for (c, m), n in unknowns.most_common()]

    changes = json.loads((ROOT / "outputs/changes.json").read_text(encoding="utf-8"))
    out_changes = {k: {"affected": len(v["affected_address_ids"]), "conflicts": len(v["conflict_flag_address_ids"]),
                       "notes": v["notes"], "affected_address_ids": v["affected_address_ids"]} for k, v in changes.items()}

    bundle = {"disclaimer": DISCLAIMER, "default_as_of": "2026-10-01", "as_of_dates": AS_OF_DATES,
              "categories": CATEGORIES, "jurisdictions": JURISDICTIONS, "rules": out_rules,
              "addresses": out_addr, "results": results, "coverage": cov, "unknowns": unknown_rows,
              "changes": out_changes}
    out = ROOT / "outputs/app/navigator_data.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(bundle, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{out.relative_to(ROOT)} · {out.stat().st_size / 1e6:.1f} MB · {len(out_rules)} rules · "
          f"{len(out_addr)} addresses · {len(AS_OF_DATES)} dates · {sum(unknowns.values())} unknown answers")


if __name__ == "__main__":
    main()
