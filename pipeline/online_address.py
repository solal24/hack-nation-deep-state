"""External data · look up an address that is NOT in the 500-address sample.

Same columns as data/addresses_enriched.csv, filled from public sources only:
  1. Census Geocoder  -> matched address, lat/lon, legal city (incorporated place), county, GEOIDs, ZIP
  2. Guardrail        -> only the cities we have rules for (legal city, never postal city)
  3. Parcel/assessor  -> year built, units, use code, from the SAME public dataset the sample used for that city
Rows go to data/addresses_online.csv with provenance="public" and a warning. They are never mixed into
the deliverables (rules/lookups/changes use the supplied 500 only). Raw API responses are cached in
data/cache/online/ as an audit trail. No LLM: every value comes straight from an official API response.

Run:  python -m pipeline.online_address "1200 Mission St, San Francisco, CA"
      python -m pipeline.online_address --file addresses.txt     (one address per line)
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipeline.enrich import CENSUS, PARAMS, legal_city, normalize_street, unit_bounds
from pipeline import parcels

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data/addresses_enriched.csv"
OUT = ROOT / "data/addresses_online.csv"
CACHE = ROOT / "data/cache/online"

WARNING = ("Building facts were retrieved automatically from public parcel/assessor data and the Census Geocoder. "
           "This address is not in the supplied sample and has not been verified by a human. Not legal advice.")

# Guardrail: the 9 cities with sample addresses (and therefore rules + a known parcel source).
SUPPORTED_CITIES = set(parcels.SOURCES)

COLUMNS = ["address_id", "street_address", "postal_city", "state", "zip", "year_built", "units", "use_code",
           "use_description", "source_dataset", "retrieved_at", "legal_city", "legal_city_source",
           "legal_city_geoid", "county", "county_geoid", "zip_geocoded", "lat", "lon", "geocode_match",
           "units_min", "units_max", "units_source", "provenance",
           # extra columns for public rows
           "query", "parcel_id", "parcel_source_url", "parcel_match", "warning"]


class OutOfScope(Exception):
    """Address resolves outside the cities we cover, or can't be resolved at all."""


def _cached_get(url, params, key):
    """GET with an on-disk cache (audit trail + no repeated hits on public APIs)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def _key(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:12]


def geocode(query):
    """Free-text address -> dict with matched address, coordinates, legal city, county. Raises OutOfScope."""
    data = _cached_get(f"{CENSUS}/onelineaddress",
                       {**PARAMS, "format": "json", "layers": "Incorporated Places,Counties", "address": query},
                       f"census_{_key(query.upper().strip())}")
    matches = data["result"]["addressMatches"]
    if not matches:
        raise OutOfScope(f"Census Geocoder found no match for {query!r}. Check the spelling or add the ZIP code.")
    places = {((m["geographies"].get("Incorporated Places") or [{}])[0].get("NAME")) for m in matches}
    if len(places) > 1:
        raise OutOfScope(f"Ambiguous address, matches in several places: {sorted(p or 'unincorporated' for p in places)}. "
                         "Add the city and ZIP code.")
    m = matches[0]
    comp, g = m["addressComponents"], m["geographies"]
    place = (g.get("Incorporated Places") or [{}])[0]
    county = (g.get("Counties") or [{}])[0]
    state = comp.get("state", "")
    status = "Match:oneline" if len(matches) == 1 else f"Match:oneline_{len(matches)}_same_place"
    if street_differs(query, comp):
        status += "_street_differs"   # geocoder fuzzy-matched, e.g. "1 Broadway" -> "1 BROADWAY CT": ask the user
    return {
        "matched_address": m["matchedAddress"],
        "street_address": m["matchedAddress"].split(",")[0].strip(),
        "number": m["matchedAddress"].split()[0],
        "street_name": comp.get("streetName", "").upper(),
        "suffix": comp.get("suffixType", "").upper(),
        "postal_city": comp.get("city", "").title(),
        "state": state,
        "zip": comp.get("zip", ""),
        "lat": m["coordinates"]["y"], "lon": m["coordinates"]["x"],
        "legal_city": legal_city(place.get("NAME"), state),
        "legal_city_geoid": place.get("GEOID", ""),
        "county": county.get("NAME", ""), "county_geoid": county.get("GEOID", ""),
        "geocode_match": status,
    }


SUFFIXES = {"STREET": "ST", "AVENUE": "AVE", "AV": "AVE", "COURT": "CT", "PLACE": "PL", "ROAD": "RD",
            "BOULEVARD": "BLVD", "DRIVE": "DR", "LANE": "LN", "TERRACE": "TER", "PARKWAY": "PKWY",
            "SQUARE": "SQ", "HIGHWAY": "HWY", "CIRCLE": "CIR", "ALLEY": "ALY", "WAY": "WAY"}


def street_differs(query, comp):
    """True when the geocoder's street name or suffix isn't what the user typed (a missing suffix counts:
    "1 Broadway" could be BROADWAY or BROADWAY CT, so we ask rather than guess)."""
    asked = {SUFFIXES.get(t, t) for t in re.sub(r"[^A-Z0-9 ]", " ", query.upper().split(",")[0]).split()}
    name = set(comp.get("streetName", "").upper().split())
    suffix = comp.get("suffixType", "").upper()
    return not name <= asked or bool(suffix and SUFFIXES.get(suffix, suffix) not in asked)


def _meters(lat1, lon1, lat2, lon2):
    dy = (lat1 - lat2) * 111_320
    dx = (lon1 - lon2) * 111_320 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def in_sample(geo):
    """Return the supplied row if this address is already one of the 500 (same city, within 15 m)."""
    with SAMPLE.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["legal_city"] == geo["legal_city"] and r["lat"] and \
                    _meters(float(r["lat"]), float(r["lon"]), geo["lat"], geo["lon"]) < 15:
                return r
    return None


def load_online():
    if not OUT.exists():
        return {}
    with OUT.open(encoding="utf-8") as f:
        return {r["address_id"]: r for r in csv.DictReader(f)}


def save_online(rows):
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["address_id"]))


def lookup(query, save=True):
    """Address string -> row dict. Sample rows come back unchanged (provenance=supplied)."""
    geo = geocode(query)
    if geo["legal_city"] not in SUPPORTED_CITIES:
        raise OutOfScope(f"{geo['matched_address']} is in {geo['legal_city'] or 'an unincorporated area'}, "
                         f"outside the cities we cover: {', '.join(sorted(SUPPORTED_CITIES))}.")
    hit = in_sample(geo)
    if hit:
        return hit

    address_id = "P" + _key(geo["matched_address"])[:8].upper()   # stable id, 'P' = public
    parcel = parcels.fetch(geo, cache=lambda url, params, tag: _cached_get(url, params, f"{tag}_{address_id}"))
    row = {
        "address_id": address_id,
        "street_address": geo["street_address"], "postal_city": geo["postal_city"], "state": geo["state"],
        "zip": parcel.get("zip") or geo["zip"],
        "year_built": parcel.get("year_built", ""), "units": parcel.get("units", ""),
        "use_code": parcel.get("use_code", ""), "use_description": parcel.get("use_description", ""),
        "source_dataset": parcels.SOURCES[geo["legal_city"]]["dataset"],
        "retrieved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "legal_city": geo["legal_city"], "legal_city_source": "census_oneline",
        "legal_city_geoid": geo["legal_city_geoid"], "county": geo["county"], "county_geoid": geo["county_geoid"],
        "zip_geocoded": geo["zip"], "lat": geo["lat"], "lon": geo["lon"], "geocode_match": geo["geocode_match"],
        "provenance": "public",
        "query": query, "parcel_id": parcel.get("parcel_id", ""),
        "parcel_source_url": parcel.get("source_url", ""), "parcel_match": parcel.get("match", "no_parcel_found"),
        "warning": WARNING,
    }
    umin, umax, usrc = unit_bounds({k: str(row[k] or "") for k in ("units", "use_code", "use_description", "source_dataset")})
    row.update(units_min="" if umin is None else umin, units_max="" if umax is None else umax,
               units_source="parcel" if usrc == "supplied" else usrc)   # never claim RealPage supplied it

    if save:
        rows = load_online()
        rows[address_id] = row
        save_online(rows)
    return row


def validate(per_city):
    """Accuracy check: re-fetch sample addresses as if they were new, compare with the supplied values."""
    with SAMPLE.open(encoding="utf-8") as f:
        sample = list(csv.DictReader(f))
    by_city = {}
    for r in sample:
        if r["legal_city"] in SUPPORTED_CITIES and parcels.SOURCES[r["legal_city"]].get("fetch"):
            by_city.setdefault(r["legal_city"], []).append(r)
    total = collections.Counter()
    for city, rows in sorted(by_city.items()):
        score = collections.Counter()
        for r in rows[:per_city]:
            q = f"{normalize_street(r['street_address'])}, {r['postal_city']}, {r['state']} {r['zip']}".strip()
            try:
                geo = geocode(q)
            except OutOfScope:
                score["geocode_failed"] += 1
                continue
            p = parcels.fetch({**geo, "legal_city": city},
                              cache=lambda url, params, tag: _cached_get(url, params, f"{tag}_val_{r['address_id']}"))
            if p["match"] == "no_parcel_found":
                score["no_parcel"] += 1
                print(f"  miss  {r['address_id']} {q}")
                continue
            score["found"] += 1
            for col in ("year_built", "units", "use_code"):
                same = str(p.get(col, "")).strip() == r[col].strip()
                score[f"{col}_ok"] += same
                if not same:
                    print(f"  diff  {r['address_id']} {col}: sample={r[col]!r} online={p.get(col)!r}  ({q})")
        n = min(per_city, len(rows))
        print(f"{city:18} found {score['found']}/{n} · year {score['year_built_ok']}/{score['found']} · "
              f"units {score['units_ok']}/{score['found']} · use {score['use_code_ok']}/{score['found']} · "
              f"no parcel {score['no_parcel']} · geocode failed {score['geocode_failed']}")
        total.update(score)
    print(f"{'TOTAL':18} found {total['found']} · year {total['year_built_ok']} · units {total['units_ok']} · "
          f"use {total['use_code_ok']} · no parcel {total['no_parcel']} · geocode failed {total['geocode_failed']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("address", nargs="?", help="free-text address")
    ap.add_argument("--file", help="text file, one address per line")
    ap.add_argument("--validate", type=int, metavar="N", help="accuracy check on N sample addresses per city")
    args = ap.parse_args()
    if args.validate:
        return validate(args.validate)
    queries = [args.address] if args.address else \
        [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    for q in queries:
        try:
            r = lookup(q)
        except OutOfScope as e:
            print(f"OUT OF SCOPE  {q}\n  {e}")
            continue
        print(f"{r['address_id']:10} {r['street_address']}, {r['legal_city']}  [{r['provenance']}]")
        print(f"  year_built={r['year_built'] or '?'} units={r['units'] or '?'} "
              f"(bounds {r['units_min'] or '?'}-{r['units_max'] or '?'}, {r['units_source']}) "
              f"use={r['use_code']} {r['use_description']!r}")
        if r["geocode_match"].endswith("street_differs"):
            print(f"  ? you typed {q!r}: confirm this is the right street before trusting the facts below")
        if r["provenance"] == "public":
            print(f"  parcel: {r['parcel_match']} {r['parcel_id']} via {r['source_dataset']}")
            print(f"  ⚠ {r['warning']}")
    if OUT.exists():
        print(f"\n-> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
