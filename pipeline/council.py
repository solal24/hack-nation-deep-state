"""External data · city council monitor (local ordinances in progress) via the public Legistar Web API.

Only cities with a live, keyless Legistar feed are monitored (checked 2026-10-03):
  Boston (boston), Newark (newark): current data · Hoboken (hobokennj): onboarding, test records only so far.
The other cities have no machine-readable feed (SF's Legistar API stopped in 2020; LA, San Diego, Berkeley,
Jersey City and Cambridge use other systems): they are listed in the output as "not monitored" with where a
human should look, rather than scraped.
Writes data/external/council_matters.json. provenance="public", review_status="unreviewed", never an input
to the deliverables. Categories reuse the keyword rules of pipeline.legislation.

Run: python -m pipeline.council            (uses cache; --refresh to re-query)
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipeline.legislation import HOUSING, _cached, categories_for

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/external/council_matters.json"
API = "https://webapi.legistar.com/v1"
SINCE = "2026-01-01"

MONITORED = {"Boston, MA": "boston", "Newark, NJ": "newark", "Hoboken, NJ": "hobokennj"}
NOT_MONITORED = {
    "San Francisco, CA": "Legistar web API not updated since 2020: check sfbos.org / sfgov.legistar.com",
    "Los Angeles, CA": "City Clerk Council File Management System (cityclerk.lacity.org), no public JSON API",
    "San Diego, CA": "No Legistar; city clerk agenda system, no public JSON API found",
    "Berkeley, CA": "No Legistar; agendas on berkeleyca.gov, no public JSON API found",
    "Jersey City, NJ": "No Legistar; city clerk site, no public JSON API found",
    "Cambridge, MA": "Granicus iQM2 (cambridgema.iqm2.com), no public JSON API found",
}
# Legistar substringof is case-insensitive; 'rent' alone matches 'current', 'parent'... so use phrases.
PHRASES = ["rent control", "rent stabilization", "rent increase", "tenant", "eviction", "landlord",
           "security deposit", "algorithm", "rental housing", "rent leveling"]
# Housing words alone let in tax abatements and housing contracts: require a tenant-rules signal too.
TENANT_RULES = re.compile(r"tenant|evict|landlord|rent (control|stabiliz|increase|leveling)|security deposit|"
                          r"algorithm|brokerage|application fee|screening", re.I)
ADOPTED = {"passed", "adopted", "approved", "enacted"}
CLOSED = {"filed", "withdrawn", "failed", "vetoed", "died"}

WARNING = ("Council item retrieved automatically from the city's public Legistar feed and not reviewed by a human. "
           "Items in progress are not law; adopted ordinances may take effect later. Not part of the supplied "
           "corpus. Not legal advice.")


def legistar(client, path, params, tag, refresh):
    def fetch():
        r = requests.get(f"{API}/{client}/{path}", params=params, timeout=60)
        r.raise_for_status()
        return r.json()
    return _cached(f"legistar_{client}_{tag}", fetch, refresh)


def status_of(m):
    s = (m.get("MatterStatusName") or "").lower()
    if m.get("MatterPassedDate") or any(w in s for w in ADOPTED):
        return "adopted"
    if any(w in s for w in CLOSED):
        return "closed"
    return "in_progress"


def build(refresh=False):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    words = " or ".join(f"substringof('{p}',MatterTitle)" for p in PHRASES)
    out = []
    for city, client in MONITORED.items():
        matters = legistar(client, "matters", {
            "$filter": f"MatterIntroDate ge datetime'{SINCE}' and ({words})",
            "$orderby": "MatterIntroDate desc", "$top": 1000}, "matters", refresh)
        for m in matters:
            title = re.sub(r"\s+", " ", (m.get("MatterTitle") or m.get("MatterName") or "").replace("﻿", "")).strip()
            if not HOUSING.search(title) or not (categories_for(title) or TENANT_RULES.search(title))                     or re.search(r"tax abatement", title, re.I):
                continue
            is_ordinance = "ordinance" in (m.get("MatterTypeName") or "").lower() or "ORDINANCE" in title[:200].upper()
            history = []
            if is_ordinance:   # one extra call per ordinance only
                history = [{"date": (h.get("MatterHistoryActionDate") or "")[:10], "body": h.get("MatterHistoryActionBodyName"),
                            "action": h.get("MatterHistoryActionName"), "result": h.get("MatterHistoryPassedFlagName")}
                           for h in legistar(client, f"matters/{m['MatterId']}/histories", {}, f"hist_{m['MatterId']}", refresh)]
            out.append({
                "matter_key": f"{client}-{m.get('MatterFile')}", "jurisdiction": city, "file": m.get("MatterFile"),
                "type": m.get("MatterTypeName"), "is_ordinance": is_ordinance, "title": title,
                "categories": categories_for(title) or ["other_tenant_housing"],
                "status": status_of(m), "legistar_status": m.get("MatterStatusName"),
                "intro_date": (m.get("MatterIntroDate") or "")[:10], "agenda_date": (m.get("MatterAgendaDate") or "")[:10],
                "passed_date": (m.get("MatterPassedDate") or "")[:10],
                "history": sorted(history, key=lambda h: h["date"]),
                "url": f"https://{client}.legistar.com/LegislationDetail.aspx?ID={m['MatterId']}&GUID={m['MatterGuid']}",
                "retrieved_at": now, "provenance": "public", "review_status": "unreviewed",
                "sources": [f"Legistar Web API ({client})"], "warning": WARNING})
    return {"monitored": MONITORED, "not_monitored": NOT_MONITORED, "since": SINCE, "matters": out}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    data = build(args.refresh)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    ms = data["matters"]
    print(f"{len(ms)} council items since {SINCE} -> {OUT.relative_to(ROOT)}")

    # Add the city level to the watchlist written by pipeline.legislation (state level): one file for the app.
    wl_path = OUT.parent / "watchlist.json"
    wl = json.loads(wl_path.read_text(encoding="utf-8")) if wl_path.exists() else {}
    for city in list(MONITORED) + list(NOT_MONITORED):
        items = [{"item": f"{m['jurisdiction']} council {m['file']}", "title": m["title"], "type": m["type"],
                  "is_ordinance": m["is_ordinance"], "categories": m["categories"], "status": m["status"],
                  "last_action_date": (m["history"][-1]["date"] if m["history"] else m["passed_date"] or m["intro_date"]),
                  "link": m["url"], "warning": m["warning"]}
                 for m in ms if m["jurisdiction"] == city]
        items.sort(key=lambda x: (not x["is_ordinance"], x["status"] != "in_progress", x["last_action_date"]))
        wl[city] = {"council_monitoring": "monitored" if city in MONITORED else NOT_MONITORED[city], "items": items}
    wl_path.write_text(json.dumps(wl, indent=1), encoding="utf-8")
    print(f"watchlist: {sum(len(v['items']) for k, v in wl.items() if ',' in k)} city items added -> {wl_path.relative_to(ROOT)}")
    for m in sorted(ms, key=lambda m: (m["jurisdiction"], not m["is_ordinance"], m["intro_date"]), reverse=False):
        print(f"  {m['jurisdiction']:11} {m['file']:10} {'ORD' if m['is_ordinance'] else '   '} {m['status']:11} "
              f"{m['intro_date']} {','.join(c.split('_')[0] for c in m['categories']):14} {m['title'][:70]}")
    print("not monitored:", ", ".join(data["not_monitored"]))


if __name__ == "__main__":
    main()
