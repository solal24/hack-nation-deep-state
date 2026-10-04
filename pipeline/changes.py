"""Step 3 · Change tests T1-T5 (starter/dev/change_tests.json) -> outputs/changes.json.

Each test names answer-key rule ids (e.g. CA-ALG-01, HOB-ALG-01, MA-ALG-P1). We map them to our
extracted rules by jurisdiction + category (+ status / bill number), run the engine on all 500
addresses at the test's dates, and report affected addresses and conflict flags.
Run: python -m pipeline.changes
"""
import json
import re
from pathlib import Path

from pipeline.engine import ROOT, load_addresses, load_rules, lookup

TESTS = ROOT / "starter/dev/change_tests.json"
OUT = ROOT / "outputs/changes.json"

PREFIX = {"CA": "CA", "NJ": "NJ", "MA": "MA", "HOB": "Hoboken, NJ", "JC": "Jersey City, NJ"}
CATEGORY = {"ALG": "algorithmic_rent_setting", "RENT": "rent_increase_limits"}
BILL_HINTS = {"MA-ALG-P1": "2983", "MA-ALG-P2": "5222", "MA-RENT-P1": "25-21"}


def resolve(key_id, rules):
    """Answer-key id -> our team_rule_ids (may be several, e.g. same law extracted from 2 docs)."""
    pre, cat, num = re.match(r"([A-Z]+)-([A-Z]+)-(P?\d+)", key_id).groups()
    cands = [r for r in rules if r["jurisdiction"] == PREFIX[pre] and r["category"] == CATEGORY[cat]]
    if num.startswith("P"):  # proposals: pending bills or failed ballot questions
        cands = [r for r in cands if r["status"] in ("pending", "failed")]
        hint = BILL_HINTS.get(key_id)
        hinted = [r for r in cands if hint and (hint in r["citation"] or hint in r.get("title", ""))]
        cands = hinted or cands
    else:
        cands = [r for r in cands if r["status"] in ("in_force", "not_yet_effective")]
    return [r["team_rule_id"] for r in cands]


def results_for(rule_ids, addresses, rules, as_of):
    """{address_id: {team_rule_id: lookup row}} for the given rules on one date."""
    out = {}
    for aid, row in addresses.items():
        rows = {r["team_rule_id"]: r for r in lookup(row, rules, as_of) if r["team_rule_id"] in rule_ids}
        if rows:
            out[aid] = rows
    return out


def run_test(t, addresses, rules):
    mapping = {k: resolve(k, rules) for k in t["rule_ids"]}
    ids = {i for v in mapping.values() for i in v}
    missing = [k for k, v in mapping.items() if not v]
    entry = {"rule_mapping": mapping, "notes": ""}

    if t["type"] == "as_of":
        before = results_for(ids, addresses, rules, t["as_of_before"])
        after = results_for(ids, addresses, rules, t["as_of_after"])
        affected = sorted(a for a in after if any(r["result"] in ("applies", "unknown") for r in after[a].values()))
        flagged = sorted({a for res in (before, after) for a, rows in res.items() if any(r["conflict_flag"] for r in rows.values())})
        nye_before = sum(any(r["result"] == "not_yet_effective" for r in rows.values()) for rows in before.values())
        entry["notes"] = (f"{t['as_of_before']}: {nye_before} addresses not_yet_effective; "
                          f"{t['as_of_after']}: {len(affected)} addresses applies/unknown.")
    elif t["type"] == "boundary":
        now = results_for(ids, addresses, rules, t["as_of"])
        affected = sorted(now)
        flagged = sorted(a for a, rows in now.items() if any(r["conflict_flag"] for r in rows.values()))
        per = {k: sorted(a for a, rows in now.items() if set(rows) & set(v)) for k, v in mapping.items()}
        cities = {k: sorted({addresses[a]["legal_city"] for a in v}) for k, v in per.items()}
        entry["per_rule"] = per
        entry["notes"] = "; ".join(f"{k}: {len(per[k])} addresses in {cities[k]}" for k in per)
    elif t["type"] == "pending":
        now = results_for(ids, addresses, rules, t["as_of"])
        affected = sorted(a for a, rows in now.items() if any(r["result"] == "pending" for r in rows.values()))
        flagged = []
        entry["notes"] = f"Pending, not in force: {len(affected)} addresses would be affected if enacted."
    else:  # negative: the proposal failed, nothing may change
        now = results_for(ids, addresses, rules, t["as_of"])
        affected, flagged = [], []
        states = set(t.get("states", []))
        by_id = {r["team_rule_id"]: r for r in rules}
        caps = sorted({a for a, row in addresses.items() if row["state"] in states
                       for r in lookup(row, rules, t["as_of"])
                       if r["result"] == "applies" and by_id[r["team_rule_id"]]["category"] == "rent_increase_limits"
                       and by_id[r["team_rule_id"]]["level"] == "city"})
        failed = [i for i in ids if any(r["team_rule_id"] == i and r["status"] == "failed" for r in rules)]
        entry["notes"] = (f"Recorded as failed: {failed or 'NO failed record extracted yet'}. "
                          f"Local rent caps applying in {sorted(states)}: {len(caps)} (must be 0).")
        if now:
            entry["notes"] += f" WARNING: {len(now)} addresses still list the failed proposal."
    if missing:
        entry["notes"] += f" Missing rules (not extracted yet): {missing}."
    entry["affected_address_ids"] = affected
    entry["conflict_flag_address_ids"] = flagged
    return entry


def main():
    rules = load_rules()
    addresses = load_addresses()
    tests = json.loads(TESTS.read_text(encoding="utf-8"))
    out = {t["test_id"]: run_test(t, addresses, rules) for t in tests}
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")

    # built-in checks against what the tests expect on this sample
    by_state = lambda s: sum(r["state"] == s for r in addresses.values())
    by_city = lambda c: sum(r["legal_city"] == c for r in addresses.values())
    expected = {"T1": by_state("CA"), "T3": by_state("NJ"), "T4": by_state("MA"), "T5": 0}
    print(f"changes.json written ({OUT.relative_to(ROOT)})")
    for tid, e in out.items():
        n = len(e["affected_address_ids"])
        exp = expected.get(tid)
        ok = "" if exp is None else ("  OK" if n == exp else f"  FAIL expected {exp}")
        print(f"  {tid}: affected {n}, conflict flags {len(e['conflict_flag_address_ids'])}{ok} · {e['notes']}")
    t2 = out.get("T2", {}).get("per_rule", {})
    if t2:
        print(f"  T2 check: HOB {len(t2.get('HOB-ALG-01', []))} (expect {by_city('Hoboken, NJ')}), "
              f"JC {len(t2.get('JC-ALG-01', []))} (expect {by_city('Jersey City, NJ')}), Newark must be 0")
    t3 = out.get("T3", {})
    if t3:
        exp = by_city("Jersey City, NJ") + by_city("Hoboken, NJ")
        print(f"  T3 check: conflict flags {len(t3['conflict_flag_address_ids'])} (expect {exp}: Jersey City + Hoboken only)")


if __name__ == "__main__":
    main()
