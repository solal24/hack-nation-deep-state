"""One call for the app: address + date -> verdicts, what's coming, and every warning the user must see.

answer(query, as_of, year_built=None, units=None) -> dict
  query: a sample id ("A0016") or any free-text address in our 9 cities.
  1. Address: the supplied row if it is one of the 500, else pipeline.online_address (Census + public parcel
     data, provenance "public"); facts the user types (year_built / units) override, provenance "user".
     Out-of-scope addresses are refused with a reason code and a message (online_address.check_scope).
  2. Verdicts: pipeline.engine.lookup on the OFFICIAL rules (outputs/rules.json, supplied corpus only).
     A verdict that depends on a building fact from public data or from the user carries that warning.
  3. Additional rules: rules only in outputs/rules_all.json (corpus_extra, review_status "to_review"),
     listed separately, each with a warning. Never mixed into the verdicts.
  4. What's coming: data/external/watchlist.json for the state and the city, each item with its warning.
  5. warnings: every distinct warning in the response + the disclaimer, for one banner on screen.
check_warnings() enforces the rule "anything not from the supplied data carries a warning": answer() raises
if it would return an item without one.

Run: python -m pipeline.answer "50 Bowdoin St, Dorchester, MA 02124" [--as-of 2027-07-02] [--year 1960 --units 6] [--json]
     python -m pipeline.answer --selftest
"""
import argparse
import json
import re
from pathlib import Path

from pipeline import engine, online_address
from pipeline.online_address import OutOfScope

ROOT = Path(__file__).resolve().parent.parent
RULES_ALL = ROOT / "outputs/rules_all.json"
WATCHLIST = ROOT / "data/external/watchlist.json"

USER_WARNING = "Based on building facts you entered, which have not been verified. Not legal advice."
EXTRA_RULE_WARNING = ("Rule extracted from a public document we retrieved online, outside the supplied corpus, and "
                      "not yet reviewed by a human. Not legal advice.")
YEAR_KEYS = {"built_before", "built_after", "exempt_if_built_within_years"}
UNIT_KEYS = {"min_units", "max_units", "excludes_single_family", "excludes_owner_occupied_min_units"}


def _load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def resolve(query, year_built=None, units=None):
    """-> (row, facts_provenance). Raises OutOfScope."""
    if re.fullmatch(r"A\d{4}", query.strip()):
        row = engine.load_addresses().get(query.strip())
        if row is None:
            raise OutOfScope("not_found", f"{query} is not one of the 500 sample address ids.")
    else:
        row = online_address.lookup(query)
    row = dict(row)
    base = "supplied" if row.get("provenance", "supplied") == "supplied" else "public"
    prov = {"year_built": base if row.get("year_built") else "missing",
            "units": base if (row.get("units_min") or row.get("units_max")) else "missing"}
    if year_built is not None:
        row["year_built"], prov["year_built"] = str(year_built), "user"
    if units is not None:
        row["units_min"] = row["units_max"] = str(units)
        row["units_source"], prov["units"] = "user", "user"
    return row, prov


def facts_used(rule):
    cond = rule.get("coverage_conditions")
    if not isinstance(cond, dict):
        return []
    return [f for f, keys in (("year_built", YEAR_KEYS), ("units", UNIT_KEYS)) if keys & {k for k, v in cond.items() if v}]


def from_outside_corpus(rule):
    """Rule extracted from a document we fetched (corpus_extra), not from the supplied corpus."""
    return rule.get("provenance", "starter") != "starter"


def verdict(res, rule, prov, row, extra=False):
    extra = extra or from_outside_corpus(rule)   # by origin, so it holds even if SOURCES=all makes it official
    used = facts_used(rule)
    basis = {f: prov[f] for f in used}
    warnings = []
    if "public" in basis.values():
        warnings.append(row.get("warning") or online_address.WARNING)
    if "user" in basis.values():
        warnings.append(USER_WARNING)
    if extra:
        warnings.insert(0, EXTRA_RULE_WARNING)
    return {**{k: res.get(k) for k in ("team_rule_id", "result", "explanation", "conflict_flag", "missing_facts")},
            "category": rule.get("category"), "title": rule.get("title"), "citation": rule.get("citation"),
            "quoted_span": rule.get("quoted_span"), "source_url": rule.get("source_url"),
            "source_retrieved_at": rule.get("retrieved_at"),
            "rule_source": "supplied corpus" if not extra else f"public ({rule.get('provenance')})",
            "rule_provenance": rule.get("provenance", "starter"),
            "review_status": rule.get("review_status"), "depends_on_facts": basis, "warnings": warnings}


def whats_coming(row):
    wl = _load_json(WATCHLIST, {})
    state = [dict(i, warnings=[i["warning"]]) for i in wl.get(row["state"], []) if i["status"] in ("pending", "enacted")]
    city_entry = wl.get(row.get("legal_city") or "", {"council_monitoring": "not monitored", "items": []})
    city = [dict(i, warnings=[i["warning"]]) for i in city_entry["items"]
            if i["is_ordinance"] or i["status"] == "in_progress"]
    return {"state_bills": state, "city_council": city, "city_council_monitoring": city_entry["council_monitoring"]}


def check_warnings(resp):
    """Problems = items built from non-supplied data that lack a warning. Empty list = OK."""
    problems = []
    addr = resp.get("address") or {}
    if addr.get("provenance") not in (None, "supplied") and not addr.get("warning"):
        problems.append(f"address {addr.get('address_id')}: provenance {addr.get('provenance')} without warning")
    for v in resp.get("verdicts", []) + resp.get("additional_rules_unreviewed", []):
        if v["rule_provenance"] != "starter" and EXTRA_RULE_WARNING not in v["warnings"]:
            problems.append(f"rule {v['team_rule_id']} from {v['rule_provenance']} without the outside-source warning")
    for v in resp.get("verdicts", []):
        if set(v["depends_on_facts"].values()) & {"public", "user"} and not v["warnings"]:
            problems.append(f"verdict {v['team_rule_id']}: depends on {v['depends_on_facts']} without warning")
    for v in resp.get("additional_rules_unreviewed", []):
        if not v["warnings"]:
            problems.append(f"additional rule {v['team_rule_id']} without warning")
    for part in ("state_bills", "city_council"):
        for i in (resp.get("whats_coming") or {}).get(part, []):
            if not i.get("warnings") or not i["warnings"][0]:
                problems.append(f"{part} item {i.get('bill') or i.get('item')} without warning")
    if engine.DISCLAIMER not in resp.get("warnings", []):
        problems.append("disclaimer missing")
    return problems


def answer(query, as_of=engine.DEFAULT_AS_OF, year_built=None, units=None):
    try:
        row, prov = resolve(query, year_built, units)
    except OutOfScope as e:
        return {"query": query, "as_of": as_of, "status": "out_of_scope", "reason": e.reason, "message": str(e),
                "warnings": [engine.DISCLAIMER]}
    official = engine.load_rules()
    all_rules = _load_json(RULES_ALL, {"rules": official})["rules"]
    by_id = {r["team_rule_id"]: r for r in all_rules} | {r["team_rule_id"]: r for r in official}
    verdicts = [verdict(r, by_id[r["team_rule_id"]], prov, row) for r in engine.lookup(row, official, as_of)]
    official_ids = {r["team_rule_id"] for r in official}
    extra_rules = [r for r in all_rules if r["team_rule_id"] not in official_ids]
    additional = [verdict(r, by_id[r["team_rule_id"]], prov, row, extra=True)
                  for r in engine.lookup(row, official + extra_rules, as_of) if r["team_rule_id"] not in official_ids]
    address = {k: row.get(k, "") for k in ("address_id", "street_address", "postal_city", "state", "zip", "legal_city",
                                           "year_built", "units_min", "units_max", "use_code", "use_description",
                                           "source_dataset", "provenance", "parcel_source_url", "geocode_match")}
    address["facts_provenance"] = prov
    address["warning"] = row.get("warning", "") if address["provenance"] != "supplied" else ""
    if "user" in prov.values():
        address["warning"] = " ".join(w for w in (address["warning"], USER_WARNING) if w)
    if address["geocode_match"].endswith("street_differs"):
        address["confirm"] = f"We matched {row['street_address']}: please confirm this is the right building."
    resp = {"query": query, "as_of": as_of, "status": "ok", "address": address, "verdicts": verdicts,
            "additional_rules_unreviewed": additional, "whats_coming": whats_coming(row)}
    seen = [address["warning"]] + [w for v in verdicts + additional for w in v["warnings"]] + \
           [i["warning"] for part in ("state_bills", "city_council") for i in resp["whats_coming"][part]]
    resp["warnings"] = list(dict.fromkeys(w for w in seen if w)) + [engine.DISCLAIMER]
    problems = check_warnings(resp)
    if problems:
        raise AssertionError("answer() would show unflagged non-supplied data: " + "; ".join(problems))
    return resp


def show(resp):
    if resp["status"] != "ok":
        print(f"OUT OF SCOPE ({resp['reason']}): {resp['message']}\n{resp['warnings'][-1]}")
        return
    a = resp["address"]
    print(f"{a['street_address']} -> {a['legal_city']} · as of {resp['as_of']} · address data: {a['provenance']} "
          f"· year built {a['year_built'] or '?'} ({a['facts_provenance']['year_built']}) "
          f"· units {a['units_min'] or '?'}-{a['units_max'] or '?'} ({a['facts_provenance']['units']})")
    if a.get("confirm"):
        print(f"  ? {a['confirm']}")
    print(f"\nVerdicts ({len(resp['verdicts'])}, official rules):")
    for v in resp["verdicts"]:
        flag = " [!]" if v["warnings"] else ""
        print(f"  {v['result']:<18} {v['category']:<27} {(v['title'] or '')[:60]}{flag}")
    if resp["additional_rules_unreviewed"]:
        print(f"\nAdditional rules from public sources, unreviewed ({len(resp['additional_rules_unreviewed'])}):")
        for v in resp["additional_rules_unreviewed"]:
            print(f"  {v['result']:<18} {v['category']:<27} {(v['title'] or '')[:60]} [!]")
    wc = resp["whats_coming"]
    print(f"\nWhat's coming: {len(wc['state_bills'])} state bills · {len(wc['city_council'])} council items "
          f"(council: {wc['city_council_monitoring'][:60]})")
    for i in wc["state_bills"][:5] + wc["city_council"][:3]:
        print(f"  {i['status']:<12} {i.get('bill') or i.get('item')}: {i['title'][:70]} [!]")
    print("\nWarnings shown to the user:")
    for w in resp["warnings"]:
        print(f"  WARNING: {w}")


SELFTEST = [
    ("A0016", {}, "ok"),                                          # supplied: no fact warnings
    ("50 Bowdoin St, Dorchester, MA 02124", {}, "ok"),           # public parcel data
    ("1200 Mission St, San Francisco, CA 94103", {"year_built": 1975, "units": 12}, "ok"),   # user facts
    ("93 Highland Ave, Somerville, MA", {}, "outside_cities"),
    ("1600 Pennsylvania Ave NW, Washington, DC 20500", {}, "outside_states"),
    ("20 Civic Center Plaza, Santa Ana, CA 92701", {}, "santa_ana_no_building_data"),
    ("99999 Nowhere Imaginary Rd, Boston, MA", {}, "not_found"),
]


def selftest():
    ok = True
    for q, facts, expect in SELFTEST:
        r = answer(q, **facts)
        got = r["status"] if r["status"] == "ok" else r["reason"]
        problems = check_warnings(r) if r["status"] == "ok" else []
        public = sum(bool(v["warnings"]) for v in r.get("verdicts", []))
        line = f"{'PASS' if got == expect and not problems else 'FAIL'}  {q[:45]:45} -> {got}"
        if r["status"] == "ok":
            line += (f" · {len(r['verdicts'])} verdicts ({public} with fact warnings) · "
                     f"{len(r['whats_coming']['state_bills'])}+{len(r['whats_coming']['city_council'])} coming · "
                     f"{len(r['warnings'])} banner warnings")
        print(line + (f" · {problems}" if problems else ""))
        ok &= got == expect and not problems
    print("selftest:", "all passed" if ok else "FAILED")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("query", nargs="?")
    ap.add_argument("--as-of", default=engine.DEFAULT_AS_OF)
    ap.add_argument("--year", type=int, help="year built, entered by the user")
    ap.add_argument("--units", type=int, help="number of units, entered by the user")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(0 if selftest() else 1)
    resp = answer(args.query, args.as_of, args.year, args.units)
    print(json.dumps(resp, indent=1, ensure_ascii=False)) if args.json else show(resp)


if __name__ == "__main__":
    main()
