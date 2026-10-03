"""External data · state legislation monitor (what's coming, what passed, what died).

For CA, NJ, MA and our 6 rule categories:
  1. LegiScan getSearch (current sessions) per state x category, filtered to housing bills
  2. LegiScan getBill for each hit + the bills named in the change tests (T1, T3, T4)
  3. Open States v3 as a second, independent source for the latest action (disagreements are flagged)
  4. Cross-reference: which supplied corpus documents already mention the bill
Writes data/external/bills.json (one record per bill) and data/external/watchlist.json (per jurisdiction,
for the app's "What's coming" panel). Everything is provenance="public", review_status="unreviewed":
it is a monitoring layer for humans, never an input to rules.json / lookups.json / changes.json.
No LLM: statuses come straight from the APIs; categories from keyword rules.

Run: python -m pipeline.legislation            (uses cache; --refresh to re-query)
Keys: LEGISCAN_API_KEY, OPENSTATES_API_KEY in .env
"""
import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
OUT_DIR = ROOT / "data/external"
CACHE = ROOT / "data/cache/external"
CORPUS = ROOT / "starter/corpus/text"
LEGISCAN = "https://api.legiscan.com/"
OPENSTATES = "https://v3.openstates.org/bills"

STATES = {"CA": "California", "NJ": "New Jersey", "MA": "Massachusetts"}

# LegiScan full-text search syntax (AND / OR / quotes). One query per state x category.
CATEGORY_QUERIES = {
    "rent_increase_limits": '"rent control" OR "rent stabilization" OR ("rent increase" AND tenant)',
    "just_cause_eviction": '"just cause" OR (eviction AND tenant)',
    "security_deposits": '"security deposit" AND (tenant OR rental OR landlord)',
    "application_screening_fees": '"application fee" OR "screening fee" OR ("rental application" AND fee)',
    "screening_restrictions": '"tenant screening" OR ("criminal history" AND housing) OR ("source of income" AND housing)',
    "algorithmic_rent_setting": '(algorithm OR algorithmic OR software) AND rent',
}
# Title/description must hit both a housing word and a category word (search alone is noisy:
# "algorithmic AND rent" also returns the NJ Kids Code).
HOUSING = re.compile(r"\b(rent|rental|tenan|landlord|lease|dwelling|eviction|housing|residential)", re.I)
CATEGORY_WORDS = {
    "rent_increase_limits": r"rent (control|stabiliz|increase|cap|gouging|levels)|rent.{0,20}(limit|ceiling)|maximum rent",
    "just_cause_eviction": r"just cause|evict|termination of tenancy",
    "security_deposits": r"deposit|(?<!social )securit",
    "application_screening_fees": r"fees?",
    "screening_restrictions": r"screening|applicant|criminal|source of income|credit (history|report)|"
                              r"background check|consumer report|eviction record",
    "algorithmic_rent_setting": r"algorithm|software|pricing device|price.?fixing|anticompetitive|restrict competition",
}

# Bills named in the challenge's change tests (starter/dev/change_tests.json): always tracked, even if search
# misses them, with the category of the test's rule ids (CA-ALG-01, NJ-ALG-01, MA-ALG-P1/P2).
TRACKED = {
    ("CA", "AB325"): "T1", ("CA", "SB763"): "T1",
    ("NJ", "A3497"): "T3", ("NJ", "S451"): "T3",
    ("MA", "S2983"): "T4", ("MA", "H5222"): "T4",
}
TEST_CATEGORY = {"T1": "algorithmic_rent_setting", "T3": "algorithmic_rent_setting", "T4": "algorithmic_rent_setting"}
MIN_RELEVANCE = 60
STATUS = {1: "introduced", 2: "engrossed", 3: "enrolled", 4: "passed", 5: "vetoed", 6: "failed"}

WARNING = ("Bill information was retrieved automatically from LegiScan (CC BY 4.0) and Open States and has not "
           "been reviewed by a human. Pending bills are not law; enacted bills may take effect later. "
           "This is not part of the supplied corpus and is not legal advice.")


def _cached(name, fetch, refresh=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{name}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def legiscan(op, refresh=False, **params):
    key = hashlib.sha1(json.dumps([op, params], sort_keys=True).encode()).hexdigest()[:12]

    def fetch():
        r = requests.get(LEGISCAN, params={"key": os.environ["LEGISCAN_API_KEY"], "op": op, **params}, timeout=60)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "OK":
            raise RuntimeError(f"LegiScan {op} {params}: {data.get('alert')}")
        return data
    return _cached(f"legiscan_{op}_{key}", fetch, refresh)


def openstates(state, bill_number, refresh=False):
    """Latest action for one bill from Open States (independent second source). None if not found."""
    ident = re.sub(r"^([A-Z]+)(\d+)$", r"\1 \2", bill_number)   # 'A3497' -> 'A 3497'

    def fetch():
        for attempt in range(4):
            r = requests.get(OPENSTATES, timeout=60, headers={"X-API-KEY": os.environ["OPENSTATES_API_KEY"]},
                             params={"jurisdiction": STATES[state], "identifier": ident, "sort": "updated_desc"})
            if r.status_code == 429:          # free tier is rate limited: back off
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(1.2)
            return r.json()
        return {"results": []}
    res = _cached(f"openstates_{state}_{bill_number}", fetch, refresh).get("results", [])
    if not res:
        return None
    b = res[0]
    return {"openstates_id": b["id"], "session": b["session"], "latest_action_date": b.get("latest_action_date", "")[:10],
            "latest_action": b.get("latest_action_description"), "openstates_url": b.get("openstates_url")}


def categories_for(text):
    if not HOUSING.search(text):
        return []
    return [c for c, rx in CATEGORY_WORDS.items() if re.search(rx, text, re.I)]


def our_status(bill, last_action):
    """LegiScan status -> monitoring status. A bill not passed when the session ended is dead."""
    s = STATUS.get(bill["status"], "unknown")
    if s != "passed" and (last_action or "").lower().startswith("substituted by"):
        return "replaced_by_substitute"   # NJ: the other chamber's identical bill moved instead
    if s == "passed":
        return "enacted"               # effective date is in the text, not the API: see warning
    if s in ("vetoed", "failed"):
        return s
    if bill["session"].get("sine_die"):
        return "died_session_ended"
    return "pending"


def corpus_mentions(state, bill_number):
    """Supplied corpus docs that already mention this bill ('A3497', 'A 3497', 'A.3497', 'S.2983'...)."""
    m = re.match(r"([A-Z]+)(\d+)", bill_number)
    prefix, num = m.groups()
    rx = re.compile(rf"\b{prefix}\.?\s?{num}\b")
    return sorted(p.stem for p in CORPUS.glob("*.txt") if rx.search(p.read_text(encoding="utf-8", errors="ignore")))


def collect(refresh=False):
    """Search + tracked bills -> {bill_id: (state, categories, test_ids)}."""
    found = {}
    for state in STATES:
        for cat, query in CATEGORY_QUERIES.items():
            res = legiscan("getSearch", refresh, state=state, query=query, year=2)["searchresult"]
            for k, hit in res.items():
                if k == "summary" or hit["relevance"] < MIN_RELEVANCE:
                    continue
                if cat in categories_for(hit["title"]):
                    found.setdefault(hit["bill_id"], [state, set(), set()])[1].add(cat)
        # Search is full-text, not by bill number: resolve tracked bills through the session master list.
        master = legiscan("getMasterList", refresh, state=state)["masterlist"]
        by_number = {b["number"]: b["bill_id"] for k, b in master.items() if k != "session"}
        for (st, num), test in TRACKED.items():
            if st == state and num in by_number:
                found.setdefault(by_number[num], [state, set(), set()])[2].add(test)
    return found


def build(refresh=False):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    records = []
    for bill_id, (state, cats, tests) in sorted(collect(refresh).items()):
        b = legiscan("getBill", refresh, id=bill_id)["bill"]
        cats = cats or set(categories_for(f"{b['title']} {b['description']}"))
        cats |= {TEST_CATEGORY[t] for t in tests}
        os_ = openstates(state, b["bill_number"], refresh)
        history = sorted(b.get("history", []), key=lambda h: h["date"])
        last = history[-1] if history else {}
        status = our_status(b, last.get("action"))
        idle = (datetime.now(timezone.utc).date() - datetime.fromisoformat(last["date"]).date()).days if last else None
        agree = os_["latest_action_date"] == last["date"][:10] if os_ and last else None
        records.append({
            "bill_key": f"{state}-{b['bill_number']}",
            "state": state, "jurisdiction": state, "bill_number": b["bill_number"],
            "session": b["session"]["session_name"],
            "title": b["title"], "description": b["description"],
            "categories": sorted(cats), "change_tests": sorted(tests),
            "status": status, "legiscan_status": STATUS.get(b["status"], b["status"]),
            "status_date": b.get("status_date"),
            "last_action": last.get("action"), "last_action_date": last.get("date"),
            "days_since_last_action": idle,
            "progress": [{"date": p["date"], "event": p["event"]} for p in b.get("progress", [])],
            "texts": [{"date": t["date"], "type": t["type"], "state_link": t.get("state_link"), "legiscan_doc_id": t["doc_id"]}
                      for t in b.get("texts", [])],
            "related_bills": [f"{s['type']}: {s['sast_bill_number']}" for s in b.get("sasts", [])],
            "official_url": b.get("state_link"), "legiscan_url": b.get("url"),
            "openstates": os_, "sources_agree_on_latest_action": agree,
            "in_supplied_corpus": corpus_mentions(state, b["bill_number"]),
            "retrieved_at": now, "provenance": "public", "review_status": "unreviewed",
            "sources": ["LegiScan API (CC BY 4.0)"] + (["Open States API v3"] if os_ else []),
            "warning": WARNING,
        })
    return records


def watchlist(records):
    """Per jurisdiction: what the app shows under 'What's coming' / 'Recently changed'."""
    out = {}
    for r in records:
        if not r["categories"]:
            continue
        out.setdefault(r["jurisdiction"], []).append({
            "bill": f"{r['state']} {r['bill_number']}", "title": r["title"], "categories": r["categories"],
            "status": r["status"], "last_action": r["last_action"], "last_action_date": r["last_action_date"],
            "days_since_last_action": r["days_since_last_action"],
            "link": r["official_url"] or r["legiscan_url"], "change_tests": r["change_tests"], "warning": r["warning"]})
    order = {"enacted": 0, "pending": 1, "replaced_by_substitute": 2, "vetoed": 3, "failed": 3, "died_session_ended": 4}
    for items in out.values():
        items.sort(key=lambda x: (order.get(x["status"], 9), x["last_action_date"] or ""), reverse=False)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true", help="re-query the APIs instead of using the cache")
    args = ap.parse_args()
    records = build(args.refresh)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "bills.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    (OUT_DIR / "watchlist.json").write_text(json.dumps(watchlist(records), indent=1), encoding="utf-8")

    print(f"{len(records)} bills -> data/external/bills.json, watchlist.json")
    for r in sorted(records, key=lambda r: (r["state"], r["status"], r["bill_number"])):
        flag = "" if r["sources_agree_on_latest_action"] in (True, None) else "  [sources disagree]"
        tests = f" {','.join(r['change_tests'])}" if r["change_tests"] else ""
        print(f"  {r['state']} {r['bill_number']:7} {r['status']:19} {r['last_action_date'] or '':10} "
              f"{','.join(c.split('_')[0] for c in r['categories']):22}{tests:6} {r['title'][:60]}{flag}")


if __name__ == "__main__":
    main()
