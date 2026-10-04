"""Step 2 · Address -> applicable laws. Deterministic: no LLM in the decision.

address -> facts + jurisdiction stack -> candidate rules -> coverage (true/false/unknown)
-> date status (as_of) -> precedence (superseded) -> results with explanation + missing facts.

Run:
  python -m pipeline.engine                         # all 500 -> outputs/lookups.json
  python -m pipeline.engine --address A0001         # one sample address, printed
  python -m pipeline.engine --as-of 2027-07-02 --address A0279
  python -m pipeline.engine --dev                   # use pipeline/dev_rules.json (engine testing only)
"""
import argparse
import csv
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADDRESSES = ROOT / "data/addresses_enriched.csv"
RULES = ROOT / "outputs/rules.json"
DEV_RULES = ROOT / "pipeline/dev_rules.json"
DEFAULT_AS_OF = "2026-10-01"
DISCLAIMER = "Not legal advice. Prototype summary of public law for the Hack-Nation challenge; verify with the cited source."

FACT_LABELS = {
    "year_built": "year built",
    "certificate_of_occupancy_date": "certificate of occupancy date (the year built falls in the cutoff year)",
    "exact_construction_date": "exact construction date (the year built falls in the cutoff year)",
    "units": "number of units",
    "owner_occupancy": "whether the owner lives in the building",
}


# ---------- inputs ----------

def load_rules(dev=False):
    data = json.loads((DEV_RULES if dev else RULES).read_text(encoding="utf-8"))
    return data["rules"] if isinstance(data, dict) else data


def load_addresses():
    return {r["address_id"]: r for r in csv.DictReader(ADDRESSES.open(encoding="utf-8"))}


def facts_from_row(row):
    """Building facts from an enriched address row (None = unknown)."""
    num = lambda v: int(float(v)) if str(v).strip() else None
    return {
        "year_built": num(row.get("year_built", "")),
        "units_min": num(row.get("units_min", "")),
        "units_max": num(row.get("units_max", "")),
        "owner_occupied": None,  # never in the supplied data
    }


def jurisdiction_stack(row):
    """Keys used in rule.jurisdiction: state code and 'City, ST'."""
    stack = [row["state"]]
    if row.get("legal_city"):
        stack.append(row["legal_city"])
    return stack


# ---------- coverage: three-valued logic ----------

def _year_test(year, cutoff_iso, uses_co, before=True):
    """Is the building built before (or after) the cutoff date? -> (True|False|None, missing_fact).
    We only know the YEAR built, so the year that contains the cutoff is ambiguous -> unknown.
    A Jan 1 cutoff is not ambiguous: 'before 1980-01-01' = built in 1979 or earlier."""
    if year is None:
        return None, "year_built"
    cutoff_year = int(cutoff_iso[:4])
    jan1 = cutoff_iso[4:10] in ("", "-01", "-01-01")
    if not jan1 and year == cutoff_year:
        return None, "certificate_of_occupancy_date" if uses_co else "exact_construction_date"
    if before:
        return year < cutoff_year, None
    return (year >= cutoff_year) if jan1 else (year > cutoff_year), None


def evaluate_coverage(cond, facts, as_of):
    """-> (verdict True/False/None, missing_facts[], reasons[])."""
    if not cond or isinstance(cond, str):
        return True, [], []  # no machine-readable condition: covers every building in the jurisdiction
    results, missing, reasons = [], [], []

    def add(verdict, fact, reason):
        results.append(verdict)
        if verdict is None and fact:
            missing.append(fact)
        reasons.append(reason)

    uses_co = bool(cond.get("built_cutoff_uses_co_date"))
    if cond.get("built_before"):
        v, f = _year_test(facts["year_built"], cond["built_before"], uses_co, before=True)
        add(v, f, f"built before {cond['built_before']}")
    if cond.get("built_after"):
        v, f = _year_test(facts["year_built"], cond["built_after"], uses_co, before=False)
        add(v, f, f"built after {cond['built_after']}")
    if cond.get("exempt_if_built_within_years"):
        cutoff = f"{int(as_of[:4]) - cond['exempt_if_built_within_years']}{as_of[4:]}"
        v, f = _year_test(facts["year_built"], cutoff, uses_co, before=True)
        add(v, f, f"older than {cond['exempt_if_built_within_years']} years")

    lo, hi = facts["units_min"], facts["units_max"]
    if cond.get("min_units"):
        n = cond["min_units"]
        v = True if lo is not None and lo >= n else False if hi is not None and hi < n else None
        add(v, "units", f"at least {n} units")
    if cond.get("max_units"):
        n = cond["max_units"]
        v = True if hi is not None and hi <= n else False if lo is not None and lo > n else None
        add(v, "units", f"at most {n} units")
    if cond.get("excludes_single_family"):
        v = True if lo is not None and lo >= 2 else False if hi is not None and hi < 2 else None
        add(v, "units", "not a single-family home")
    if cond.get("excludes_owner_occupied_min_units"):
        n = cond["excludes_owner_occupied_min_units"]  # owner-occupied buildings with <= n units are exempt
        v = True if lo is not None and lo > n else None
        add(v, "owner_occupancy" if lo is not None else "units", f"not an owner-occupied building of {n} units or fewer")

    if False in results:
        return False, [], reasons
    if None in results:
        return None, sorted(set(missing)), reasons
    return True, [], reasons


# ---------- dates and precedence ----------

def status_on(rule, as_of):
    """applies | not_yet_effective | pending | None (failed / not law)."""
    if rule.get("status") == "failed":
        return None
    if rule.get("status") == "pending":
        return "pending"
    eff = rule.get("effective_date")
    if eff and (eff + "-01-01"[len(eff) - 4:])[:10] > as_of:  # '2027' / '2027-07' / '2027-07-01' -> full date
        return "not_yet_effective"
    if rule.get("status") == "not_yet_effective" and not eff:
        return "not_yet_effective"
    return "applies"


def explain(rule, result, missing, reasons, winner=None, conflict_with=None, disputed=None):
    """One plain sentence: what the rule says + why this result + citation + retrieval date."""
    what = rule.get("requirement", "").strip().rstrip(".")
    key = f" Key value: {rule['key_value']}." if rule.get("key_value") else ""
    retrieved = (rule.get("retrieved_at") or "")[:10]
    src = f" [{rule.get('citation')}{'; source retrieved ' + retrieved if retrieved else ''}]"
    if result == "unknown":
        facts = ", ".join(FACT_LABELS.get(m, m) for m in missing)
        head = f"May apply: coverage depends on {facts}, which the data does not include."
        if disputed and set(missing) <= set(disputed):   # the data has the fact, but its sources disagree
            head = f"May apply: coverage depends on {facts}, on which the sources disagree ({'; '.join(disputed.values())})."
    elif result == "not_yet_effective":
        head = f"Enacted but not yet in force: takes effect {rule.get('effective_date')}."
    elif result == "pending":
        head = "Pending bill or proposal, not law."
    elif result == "superseded":
        by = f" ({winner['title']}, {winner['citation']})" if winner else ""
        head = f"Covered, but the stricter local rule governs here{by}."
    else:
        head = f"Applies{' (building is ' + ', '.join(reasons) + ')' if reasons else ''}."
    note = f" Possible conflict with {', '.join(conflict_with)}: flagged for human review." if conflict_with else ""
    if rule.get("provenance", "starter") != "starter":   # text fetched online (corpus_extra), not supplied
        note += " Source retrieved online, outside the supplied corpus; not reviewed by a human."
    return f"{head} {what}.{key}{note}{src}"


# Local rent control governs the state rent cap (e.g. SF/LA/Berkeley over Cal. Civ. Code § 1947.12, which
# exempts units under stricter local rent control). Only cap-vs-cap: both rules must set a limit with a value.
LOCAL_GOVERNS = {"rent_increase_limits"}


def is_cap(rule):
    return bool(rule.get("sets_limit")) and bool(rule.get("key_value"))


def lookup(row, rules, as_of=DEFAULT_AS_OF, facts=None):
    """All rules that concern one address on one date. Rules that don't apply are omitted."""
    facts = facts or facts_from_row(row)
    stack = jurisdiction_stack(row)
    out = {}
    disputed = ({"units": f"{row['units_min']} to {row['units_max']} units"}
                if row.get("units_source") == "conflict" else None)   # enrich: supplied units vs use code
    for rule in rules:
        if rule["jurisdiction"] not in stack:
            continue
        status = status_on(rule, as_of)
        if status is None:
            continue
        covered, missing, reasons = evaluate_coverage(rule.get("coverage_conditions"), facts, as_of)
        if covered is False:
            continue
        result = "unknown" if covered is None and status == "applies" else status
        out[rule["team_rule_id"]] = {
            "team_rule_id": rule["team_rule_id"], "result": result,
            "missing_facts": missing if covered is None else [],
            "reasons": reasons, "conflict_flag": False, "conflict_with": [],
            "_rule": rule,
        }

    def supersede(loser, winner):
        loser.update(result="superseded", superseded_by=winner["team_rule_id"], missing_facts=[])

    # precedence 1: explicit overrides extracted from the law text
    for res in list(out.values()):
        if res["result"] == "applies":
            for other_id in res["_rule"].get("overrides") or []:
                other = out.get(other_id)
                if other and other["result"] in ("applies", "unknown"):
                    supersede(other, res)
    # precedence 2: a local rule that applies AND sets a limit governs the state rule of the same category
    for res in out.values():
        r = res["_rule"]
        if res["result"] == "applies" and r.get("level") == "city" and r["category"] in LOCAL_GOVERNS and is_cap(r):
            for other in out.values():
                o = other["_rule"]
                if o.get("level") == "state" and o["category"] == r["category"] and is_cap(o) \
                        and other["result"] in ("applies", "unknown"):
                    supersede(other, res)
    # conflicts, per address: a state rule that preempts local law + a local rule of the same category here
    live = ("applies", "unknown", "not_yet_effective", "pending")
    for res in out.values():
        r = res["_rule"]
        if r.get("preempts_local") and res["result"] in live:
            for other in out.values():
                o = other["_rule"]
                if o.get("level") == "city" and o["category"] == r["category"] and other["result"] in live:
                    res["conflict_flag"] = other["conflict_flag"] = True
                    res["conflict_with"].append(o.get("citation"))
                    other["conflict_with"].append(r.get("citation"))
        elif r.get("conflict_flag") and not r.get("preempts_local"):  # the source itself shows conflicting values/dates
            res["conflict_flag"] = True
            res["conflict_with"].append("another published value or date for this rule")
    for res in out.values():
        winner = out.get(res.get("superseded_by"), {}).get("_rule")
        res["explanation"] = explain(res["_rule"], res["result"], res["missing_facts"], res["reasons"],
                                     winner, res["conflict_with"], disputed)
    return [{k: v for k, v in r.items() if k not in ("_rule", "reasons", "conflict_with")} for r in out.values()]


# ---------- any address (outside the 500) ----------

COVERED_CITIES = {"Los Angeles, CA", "San Francisco, CA", "San Diego, CA", "Berkeley, CA", "Santa Ana, CA",
                  "Jersey City, NJ", "Hoboken, NJ", "Newark, NJ", "Boston, MA", "Cambridge, MA"}
COVERED_STATES = {"CA", "NJ", "MA"}
STATE_CODES = {"06": "CA", "34": "NJ", "25": "MA"}


def resolve_free_address(text, year_built=None, units=None):
    """Free-text address -> a row shaped like addresses_enriched.csv (live Census geocoding).
    Building facts come from the user (None = 'I don't know'); provenance = 'user'."""
    import requests  # only needed for live lookups
    resp = requests.get("https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress", timeout=60, params={
        "address": text, "benchmark": "Public_AR_Current", "vintage": "Current_Current",
        "layers": "Incorporated Places,Counties,States", "format": "json"})
    resp.raise_for_status()
    matches = resp.json()["result"]["addressMatches"]
    if not matches:
        return None
    m = matches[0]
    g = m["geographies"]
    state_fips = (g.get("States") or [{}])[0].get("STATE") or (g.get("Counties") or [{}])[0].get("STATE", "")
    state = STATE_CODES.get(state_fips, (g.get("States") or [{}])[0].get("STUSAB", ""))
    place = (g.get("Incorporated Places") or [{}])[0].get("NAME")
    from pipeline.enrich import legal_city  # same naming rule as the 500
    return {
        "address_id": "USER", "street_address": m["matchedAddress"], "postal_city": "", "state": state,
        "zip": m["addressComponents"].get("zip", ""), "legal_city": legal_city(place, state) or "",
        "legal_city_source": "census_live", "year_built": str(year_built or ""),
        "units_min": str(units or ""), "units_max": str(units or ""),
        "units_source": "user" if units else "unknown", "provenance": "user",
    }


def coverage_scope(row):
    """Is this address inside what our corpus covers? -> (in_scope, note)."""
    if row["state"] not in COVERED_STATES:
        return False, f"{row['state'] or 'This state'} is not covered by our sources (CA, NJ, MA only)."
    if row.get("legal_city") not in COVERED_CITIES:
        where = row.get("legal_city") or "an unincorporated area"
        return True, f"Only state-level rules are covered here: {where} is not one of our 10 cities, so local rules may be missing."
    return True, ""


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=DEFAULT_AS_OF)
    ap.add_argument("--address", help="address_id from the sample, e.g. A0001")
    ap.add_argument("--free", help='any address, e.g. "350 Massachusetts Ave, Cambridge, MA 02139"')
    ap.add_argument("--year", type=int, help="year built, given by the user (with --free)")
    ap.add_argument("--units", type=int, help="number of units, given by the user (with --free)")
    ap.add_argument("--dev", action="store_true", help="use dev_rules.json (engine testing only)")
    args = ap.parse_args()

    rules = load_rules(dev=args.dev)
    addresses = load_addresses()

    if args.free:
        row = resolve_free_address(args.free, args.year, args.units)
        if row is None:
            print("Address not found by the Census geocoder. Check spelling or add the ZIP code.")
            return
        in_scope, note = coverage_scope(row)
        print(f"{args.free} -> {row['street_address']} · legal city {row['legal_city'] or '(unincorporated)'} "
              f"· built {row['year_built'] or '?'} · units {row['units_min'] or '?'} · as of {args.as_of} · provenance: user")
        if note:
            print(f"  WARNING: {note}")
        if not in_scope:
            return
        for r in lookup(row, rules, args.as_of):
            flag = " [conflict]" if r["conflict_flag"] else ""
            print(f"  {r['result']:<18} {r['team_rule_id']:<14} {r['explanation']}{flag}")
        return

    print(DISCLAIMER)
    if args.address:
        row = addresses[args.address]
        print(f"{row['address_id']} · {row['street_address']}, {row['postal_city']} -> {row['legal_city']} "
              f"· built {row['year_built'] or '?'} · units {row['units_min'] or '?'}-{row['units_max'] or '?'} · as of {args.as_of}")
        for r in lookup(row, rules, args.as_of):
            flag = " [conflict]" if r["conflict_flag"] else ""
            print(f"  {r['result']:<18} {r['team_rule_id']:<14} {r['explanation']}{flag}")
        return

    lookups = {aid: [{k: r[k] for k in ("team_rule_id", "result", "explanation", "conflict_flag")}
                     for r in lookup(row, rules, args.as_of)]
               for aid, row in addresses.items()}
    name = "lookups" + ("_dev" if args.dev else "") + ("" if args.as_of == DEFAULT_AS_OF else f"_{args.as_of}")
    out = ROOT / f"outputs/{name}.json"  # never overwrite the deliverable with another as_of
    out.write_text(json.dumps({"as_of": args.as_of, "disclaimer": DISCLAIMER, "lookups": lookups}, indent=2), encoding="utf-8")
    counts = {}
    for rows in lookups.values():
        for r in rows:
            counts[r["result"]] = counts.get(r["result"], 0) + 1
    print(f"{len(lookups)} addresses -> {out.relative_to(ROOT)} · results: {counts}")


if __name__ == "__main__":
    main()
