"""Step 4 · Compact data bundle for the web app (no server, no LLM at runtime).

Writes outputs/app/navigator_data.json:
  rules      -> the fields the UI shows + the fields the client-side engine needs (sets_limit, preempts_local...)
  addresses  -> the 500 sample buildings (legal city, facts, where each fact comes from)
  results    -> engine output per address for a few as-of dates:
                [rule id, result, missing facts, conflict] (+ [superseded_by, conflict_with] when either is set)
  coverage   -> 13 jurisdictions x 6 categories matrix (rule / pending / not yet effective / none)
  unknowns   -> why answers are "unknown" (missing fact x city), for the public-office view
  changes    -> T1-T5: the test as given + our result
  radar      -> what's coming per jurisdiction, ranked by certainty (verified rules first, then the unverified
                bill / council watchlist from data/external/watchlist.json, each with its warning)
  stats      -> numbers for the methodology page, computed here (nothing typed by hand)
  demo       -> addresses that show each behaviour, for the demo and for QA
Run: python -m pipeline.app_bundle
"""
import collections
import csv
import json
from datetime import date

from pipeline.engine import DEFAULT_AS_OF, DISCLAIMER, ROOT, facts_from_row, load_addresses, load_rules, lookup

AS_OF_DATES = ["2025-12-31", "2026-01-02", "2026-10-01", "2027-07-02"]
CATEGORIES = ["rent_increase_limits", "just_cause_eviction", "security_deposits",
              "application_screening_fees", "screening_restrictions", "algorithmic_rent_setting"]
JURISDICTIONS = ["CA", "Los Angeles, CA", "San Francisco, CA", "San Diego, CA", "Berkeley, CA", "Santa Ana, CA",
                 "NJ", "Jersey City, NJ", "Hoboken, NJ", "Newark, NJ", "MA", "Boston, MA", "Cambridge, MA"]
RULE_FIELDS = ["team_rule_id", "jurisdiction", "level", "category", "status", "title", "requirement", "key_value",
               "coverage_conditions", "exemptions", "effective_date", "citation", "source_doc_id", "source_url",
               "retrieved_at", "quoted_span", "confidence", "conflict_note", "provenance", "review_status",
               "sets_limit", "preempts_local", "overrides", "conflict_flag", "penalty"]
DEMO = [("A0001", "Los Angeles 1927, 32 units: local rent control (RSO) governs, the state cap is superseded"),
        ("A0036", "Postal city 'South Boston' resolves to the legal city of Boston: no rent cap in MA, bills pending"),
        ("A0106", "San Francisco, year built missing: eviction coverage is unknown, and the app says which fact settles it"),
        ("A0008", "Jersey City: local algorithmic ban applies now; the NJ FAIR Act takes effect 2027-07-01 and is flagged as a possible conflict"),
        ("A0005", "Berkeley, no year built and units only '5+': several unknowns, each with the missing fact")]
CERTAINTY = {"scheduled": 5, "enacted": 4, "adopted": 4, "verified_pending": 3, "moving": 3, "stalled": 2, "signal": 1}


def radar(rules, as_of=DEFAULT_AS_OF):
    """What's coming, per jurisdiction. Verified rules (our corpus, quoted) first, then the unverified watchlist."""
    today = date.fromisoformat(as_of)
    out = collections.defaultdict(list)
    closed = collections.defaultdict(list)
    for r in rules:
        eff = r.get("effective_date") or ""
        if r["status"] == "pending" or (r["status"] in ("in_force", "not_yet_effective") and eff[:10] > as_of):
            out[r["jurisdiction"]].append({
                "id": r["team_rule_id"], "kind": "verified_rule", "verified": True, "rule_id": r["team_rule_id"],
                "title": r["title"], "citation": r["citation"], "categories": [r["category"]],
                "status": "pending" if r["status"] == "pending" else "enacted",
                "certainty": "verified_pending" if r["status"] == "pending" else "scheduled",
                "effective_date": eff or None, "link": r["source_url"], "warning": None})
    path = ROOT / "data/external/watchlist.json"
    watch = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for jur, entry in watch.items():
        items = entry if isinstance(entry, list) else entry.get("items", [])
        for i in items:
            last = i.get("last_action_date") or ""
            days = (today - date.fromisoformat(last)).days if last else None
            st, title = i.get("status"), i.get("title", "")
            if isinstance(entry, list):  # state bills (LegiScan / Open States)
                kind = "bill"
                if st in ("failed", "replaced_by_substitute"):
                    closed[jur].append({"id": i["bill"], "title": title, "status": st, "last_action_date": last,
                                        "link": i.get("link"), "warning": i.get("warning")})
                    continue
                if st == "enacted":
                    if days is not None and days > 180:
                        continue  # enacted 6+ months ago: already law, not "coming"
                    certainty = "enacted"
                else:
                    certainty = "moving" if days is not None and days <= 120 else "stalled"
            else:  # city council items (Legistar)
                if st == "closed":
                    continue
                kind = "ordinance" if i.get("is_ordinance") else (i.get("type") or "council item").lower()
                if i.get("is_ordinance"):
                    certainty = "adopted" if st == "adopted" else "moving"
                else:
                    certainty = "signal"  # resolutions, hearings, motions: not law, a signal of intent
            out[jur].append({
                "id": i.get("bill") or i.get("item"), "kind": kind, "verified": False, "rule_id": None,
                "title": title, "citation": i.get("bill") or i.get("item"),
                "categories": i.get("categories", []), "status": st, "certainty": certainty,
                "last_action": i.get("last_action"), "last_action_date": last or None, "days_since_last_action": days,
                "in_scope": bool(set(i.get("categories", [])) & set(CATEGORIES)),
                "change_tests": i.get("change_tests", []), "effective_date": None,
                "link": i.get("link"), "warning": i.get("warning")})
    for jur in out:
        out[jur].sort(key=lambda x: (-CERTAINTY[x["certainty"]], not x.get("in_scope", True),
                                     -(int((x.get("last_action_date") or "0000").replace("-", "")))))
    monitoring = {jur: e.get("council_monitoring") for jur, e in watch.items() if isinstance(e, dict)}
    return {"items": dict(out), "closed": dict(closed), "council_monitoring": monitoring,
            "legend": {"scheduled": "Enacted, in our verified sources, takes effect on a known date",
                       "enacted": "Signed into law recently (bill tracker); effective date to check",
                       "adopted": "Local ordinance adopted (council feed); not yet in our verified sources",
                       "verified_pending": "Pending bill whose text is in our verified sources; not law",
                       "moving": "Pending, with action in the last 120 days; not law",
                       "stalled": "Pending, no action for 120+ days; not law",
                       "signal": "Council resolution, hearing or motion; shows intent, not law"}}


def stats(rules, rows, results):
    """Numbers for the methodology page, all computed from the files."""
    verified = 0
    for r in rules:
        d = r["source_doc_id"]
        for p in (ROOT / f"starter/corpus/text/{d}.txt", ROOT / f"corpus_extra/text/{d}.txt"):
            if p.exists() and r["quoted_span"] in p.read_text(encoding="utf-8"):
                verified += 1
                break
    manifest = list(csv.DictReader((ROOT / "starter/corpus/corpus_manifest.csv").open(encoding="utf-8")))
    texts = len(list((ROOT / "starter/corpus/text").glob("*.txt")))
    extra = len(list((ROOT / "corpus_extra/text").glob("*.txt"))) if (ROOT / "corpus_extra/text").exists() else 0
    dist = collections.Counter(x[1] for rws in results[DEFAULT_AS_OF].values() for x in rws)
    return {
        "rules": len(rules), "rules_by_status": dict(collections.Counter(r["status"] for r in rules)),
        "quotes_verified": verified, "source_docs_used": len({r["source_doc_id"] for r in rules}),
        "starter_docs": len(manifest), "starter_docs_with_text": texts, "extra_official_docs": extra,
        "addresses": len(rows),
        "geocoded": sum(r["geocode_match"].startswith("Match") for r in rows.values()),
        "postal_city_corrected": sum(bool(r["legal_city"]) and r["legal_city"].split(",")[0] != r["postal_city"]
                                     for r in rows.values()),
        "year_built_known": sum(bool(r["year_built"].strip()) for r in rows.values()),
        "units_supplied": sum(r["units_source"] == "supplied" for r in rows.values()),
        "units_from_use_code": sum(r["units_source"] == "use_code" for r in rows.values()),
        "results_default_date": dict(dist), "answers_default_date": sum(dist.values()),
    }


def main():
    rules = load_rules()
    addresses = load_addresses()
    out_rules = [{k: r.get(k) for k in RULE_FIELDS} for r in rules]

    out_addr = []
    for aid, row in addresses.items():
        f = facts_from_row(row)
        out_addr.append({
            "id": aid, "street": row["street_address"], "postal_city": row["postal_city"], "state": row["state"],
            "zip": row.get("zip_geocoded") or row["zip"], "zip_supplied": row["zip"], "legal_city": row["legal_city"],
            "legal_city_source": row.get("legal_city_source"), "county": row.get("county"),
            "year_built": f["year_built"], "units_min": f["units_min"], "units_max": f["units_max"],
            "units_source": row.get("units_source"), "use_description": row["use_description"],
            "source_dataset": row["source_dataset"], "retrieved_at": row["retrieved_at"],
            "lat": row.get("lat"), "lon": row.get("lon"),
        })

    def tup(r):
        t = [r["team_rule_id"], r["result"], r["missing_facts"], r["conflict_flag"]]
        if r.get("superseded_by") or r.get("conflict_with"):
            t += [r.get("superseded_by"), sorted(set(r.get("conflict_with") or []))]
        return t

    results = {d: {aid: [tup(r) for r in lookup(row, rules, d)] for aid, row in addresses.items()}
               for d in AS_OF_DATES}

    cov = {j: {c: [] for c in CATEGORIES} for j in JURISDICTIONS}
    for r in rules:
        if r["jurisdiction"] in cov and r["category"] in CATEGORIES:
            cov[r["jurisdiction"]][r["category"]].append({"id": r["team_rule_id"], "status": r["status"]})

    unknowns = collections.Counter()
    for aid, rows in results[DEFAULT_AS_OF].items():
        for t in rows:
            if t[1] == "unknown":
                for m in t[2] or ["other"]:
                    unknowns[(addresses[aid]["legal_city"], m)] += 1
    unknown_rows = [{"city": c, "missing_fact": m, "answers": n} for (c, m), n in unknowns.most_common()]

    tests = {t["test_id"]: t for t in json.loads((ROOT / "starter/dev/change_tests.json").read_text(encoding="utf-8"))}
    changes = json.loads((ROOT / "outputs/changes.json").read_text(encoding="utf-8"))
    out_changes = {k: {"title": tests.get(k, {}).get("title"), "type": tests.get(k, {}).get("type"),
                       "expected_behavior": tests.get(k, {}).get("expected_behavior"),
                       "as_of_before": tests.get(k, {}).get("as_of_before"),
                       "as_of_after": tests.get(k, {}).get("as_of_after") or tests.get(k, {}).get("as_of"),
                       "rule_mapping": v.get("rule_mapping"), "notes": v["notes"],
                       "affected": len(v["affected_address_ids"]), "conflicts": len(v["conflict_flag_address_ids"]),
                       "affected_address_ids": v["affected_address_ids"],
                       "conflict_flag_address_ids": v["conflict_flag_address_ids"]} for k, v in changes.items()}

    bundle = {"disclaimer": DISCLAIMER, "generated_at": date.today().isoformat(), "default_as_of": DEFAULT_AS_OF,
              "as_of_dates": AS_OF_DATES, "categories": CATEGORIES, "jurisdictions": JURISDICTIONS,
              "rules": out_rules, "addresses": out_addr, "results": results, "coverage": cov,
              "unknowns": unknown_rows, "changes": out_changes, "radar": radar(rules),
              "stats": stats(rules, addresses, results),
              "demo": [{"id": a, "why": w} for a, w in DEMO if a in addresses]}
    out = ROOT / "outputs/app/navigator_data.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(bundle, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    n_radar = sum(len(v) for v in bundle["radar"]["items"].values())
    print(f"{out.relative_to(ROOT)} · {out.stat().st_size / 1e6:.1f} MB · {len(out_rules)} rules · "
          f"{len(out_addr)} addresses · {len(AS_OF_DATES)} dates · {sum(unknowns.values())} unknown answers · "
          f"{n_radar} radar items")


if __name__ == "__main__":
    main()
