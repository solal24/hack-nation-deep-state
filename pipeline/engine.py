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

FACT_LABELS = {
    "year_built": "year built",
    "certificate_of_occupancy_date": "certificate of occupancy date (the year built falls in the cutoff year)",
    "units": "number of units",
    "owner_occupancy": "whether the owner lives in the building",
}


# ---------- inputs ----------

def load_rules(dev=False):
    data = json.loads((DEV_RULES if dev else RULES).read_text())
    return data["rules"] if isinstance(data, dict) else data


def load_addresses():
    return {r["address_id"]: r for r in csv.DictReader(ADDRESSES.open())}


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
    """Is the building built before (or after) the cutoff? -> (True|False|None, missing_fact)."""
    if year is None:
        return None, "year_built"
    cutoff_year = int(cutoff_iso[:4])
    if year == cutoff_year and uses_co:
        return None, "certificate_of_occupancy_date"
    ok = year < cutoff_year or (year == cutoff_year and not uses_co) if before else year > cutoff_year
    return ok, None


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


def explain(rule, result, missing, reasons, winner=None):
    where = rule["jurisdiction"]
    if result == "unknown":
        facts = ", ".join(FACT_LABELS.get(m, m) for m in missing)
        return f"{where} rule; coverage depends on {facts}, which the data does not include."
    if result == "not_yet_effective":
        return f"Enacted in {where} but takes effect on {rule.get('effective_date')}."
    if result == "pending":
        return f"Pending in {where}: a bill or proposal, not law."
    if result == "superseded":
        by = f" ({winner['title']}, {winner['citation']})" if winner else ""
        return f"Covered, but a stricter local rule governs this category here{by}."
    cond = f" (building is {', '.join(reasons)})" if reasons else ""
    return f"{where} rule applies{cond}."


def lookup(row, rules, as_of=DEFAULT_AS_OF, facts=None):
    """All rules that concern one address on one date. Rules that don't apply are omitted."""
    facts = facts or facts_from_row(row)
    stack = jurisdiction_stack(row)
    out = {}
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
            "reasons": reasons, "conflict_flag": bool(rule.get("conflict_flag")),
            "_rule": rule,
        }
    # precedence: a rule that applies (or may apply) supersedes the rules it overrides
    for res in list(out.values()):
        if res["result"] in ("applies", "unknown"):
            for other_id in res["_rule"].get("overrides") or []:
                other = out.get(other_id)
                if other and other["result"] == "applies" and res["result"] == "applies":
                    other["result"] = "superseded"
                    other["superseded_by"] = res["team_rule_id"]
    for res in out.values():
        winner = out.get(res.get("superseded_by"), {}).get("_rule")
        res["explanation"] = explain(res["_rule"], res["result"], res["missing_facts"], res["reasons"], winner)
    return [{k: v for k, v in r.items() if k not in ("_rule", "reasons")} for r in out.values()]


# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default=DEFAULT_AS_OF)
    ap.add_argument("--address", help="address_id from the sample, e.g. A0001")
    ap.add_argument("--dev", action="store_true", help="use dev_rules.json (engine testing only)")
    args = ap.parse_args()

    rules = load_rules(dev=args.dev)
    addresses = load_addresses()

    if args.address:
        row = addresses[args.address]
        print(f"{row['address_id']} · {row['street_address']}, {row['postal_city']} -> {row['legal_city']} "
              f"· built {row['year_built'] or '?'} · units {row['units_min'] or '?'}-{row['units_max'] or '?'} · as of {args.as_of}")
        for r in lookup(row, rules, args.as_of):
            flag = " ⚑ conflict" if r["conflict_flag"] else ""
            print(f"  {r['result']:<18} {r['team_rule_id']:<14} {r['explanation']}{flag}")
        return

    lookups = {aid: [{k: r[k] for k in ("team_rule_id", "result", "explanation", "conflict_flag")}
                     for r in lookup(row, rules, args.as_of)]
               for aid, row in addresses.items()}
    out = ROOT / ("outputs/lookups_dev.json" if args.dev else "outputs/lookups.json")
    out.write_text(json.dumps({"as_of": args.as_of, "lookups": lookups}, indent=2))
    counts = {}
    for rows in lookups.values():
        for r in rows:
            counts[r["result"]] = counts.get(r["result"], 0) + 1
    print(f"{len(lookups)} addresses -> {out.relative_to(ROOT)} · results: {counts}")


if __name__ == "__main__":
    main()
