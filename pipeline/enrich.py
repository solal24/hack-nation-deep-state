"""Step 0 · Enrich the 500 sample addresses (supplied data + Census geocoding only).

Adds: legal city (Census incorporated place), county, GEOIDs, geocoded ZIP, lat/lon,
and unit bounds parsed from use codes when `units` is missing.
Output: data/addresses_enriched.csv. Census responses are cached in data/cache/.
Run: python -m pipeline.enrich
"""
import collections
import csv
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "starter/data/sample_addresses.csv"
OUT = ROOT / "data/addresses_enriched.csv"
CACHE = ROOT / "data/cache"
CENSUS = "https://geocoding.geo.census.gov/geocoder/geographies"
PARAMS = {"benchmark": "Public_AR_Current", "vintage": "Current_Current"}


def batch_geocode(rows):
    """One batch call for all addresses -> {address_id: (match, matched_address, lon, lat)}."""
    cache = CACHE / "batch.csv"
    if not cache.exists():
        buf = io.StringIO()
        w = csv.writer(buf)
        for r in rows:
            w.writerow([r["address_id"], r["street_address"], r["postal_city"], r["state"], r["zip"]])
        resp = requests.post(f"{CENSUS}/addressbatch", data=PARAMS,
                             files={"addressFile": ("a.csv", buf.getvalue())}, timeout=600)
        resp.raise_for_status()
        cache.write_text(resp.text, encoding="utf-8")
    out = {}
    for rec in csv.reader(cache.read_text(encoding="utf-8").splitlines()):
        if len(rec) >= 6 and rec[2] == "Match":
            lon, lat = rec[5].split(",")
            out[rec[0]] = (f"{rec[2]}:{rec[3]}", rec[4], float(lon), float(lat))
        elif rec:
            out[rec[0]] = (rec[2], "", None, None)
    return out


def place_for(address_id, lon, lat):
    """Incorporated place + county for a coordinate (cached per address)."""
    cache = CACHE / f"place_{address_id}.json"
    if not cache.exists():
        resp = requests.get(f"{CENSUS}/coordinates", timeout=60, params={
            **PARAMS, "x": lon, "y": lat, "layers": "Incorporated Places,Counties", "format": "json"})
        resp.raise_for_status()
        cache.write_text(json.dumps(resp.json()["result"]["geographies"]), encoding="utf-8")
    g = json.loads(cache.read_text(encoding="utf-8"))
    place = (g.get("Incorporated Places") or [{}])[0]
    county = (g.get("Counties") or [{}])[0]
    return place.get("NAME"), place.get("GEOID"), county.get("NAME"), county.get("GEOID")


BOSTON_NEIGHBORHOODS = {"Boston", "Dorchester", "Roxbury", "East Boston", "Brighton", "Allston", "South Boston",
                        "Jamaica Plain", "Hyde Park", "Mattapan", "Charlestown", "Roslindale", "West Roxbury",
                        "Mission Hill", "Back Bay", "South End", "North End", "Fenway"}


def normalize_street(street):
    """'05TH AV' -> '5TH AVE' (SF assessor format the geocoder misses)."""
    street = re.sub(r"\b0+(\d)", r"\1", street)
    return re.sub(r"\bAV\b", "AVE", street)


def oneline(r):
    """Single-address fallback (resolves batch ties). Returns match, matched, lon, lat, place tuple."""
    cache = CACHE / f"oneline_{r['address_id']}.json"
    if not cache.exists():
        resp = requests.get(f"{CENSUS}/onelineaddress", timeout=60, params={
            **PARAMS, "format": "json", "layers": "Incorporated Places,Counties",
            "address": f"{normalize_street(r['street_address'])}, {r['postal_city']}, {r['state']} {r['zip']}".strip()})
        resp.raise_for_status()
        cache.write_text(json.dumps(resp.json()["result"]["addressMatches"]), encoding="utf-8")
    matches = json.loads(cache.read_text(encoding="utf-8"))
    if not matches:
        return "No_Match", "", None, None, (None, None, None, None)
    m = matches[0]
    places = {(x.get("geographies", {}).get("Incorporated Places") or [{}])[0].get("NAME") for x in matches}
    g = m.get("geographies", {})
    place = (g.get("Incorporated Places") or [{}])[0]
    county = (g.get("Counties") or [{}])[0]
    status = "Match:oneline" if len(places) == 1 else "Tie:oneline_places_differ"
    return (status, m["matchedAddress"], m["coordinates"]["x"], m["coordinates"]["y"],
            (place.get("NAME") if len(places) == 1 else None, place.get("GEOID"), county.get("NAME"), county.get("GEOID")))


STREET_SUFFIXES = {"ST", "AVE", "AV", "RD", "DR", "BLVD", "PL", "CT", "LN", "WAY", "TER", "PKWY", "SQ", "HWY", "CIR"}


def range_fallback(r):
    """'521-523 S 17TH' -> geocode every number in the range (no supplied ZIP, 'ST' added if no suffix).
    Per number, candidates spelled exactly like the query win ('MT PROSPECT' over 'MOUNT PROSPECT').
    Accepted only if every number matches with the same ZIP, place and county. Same tuple shape as oneline()."""
    m = re.match(r"^(\d+)(?:\.\d+)?-(\d+)(?:\.\d+)?\s+(.*)$", r["street_address"].strip())  # '322-322.5' -> 322
    if not m or not 0 <= int(m.group(2)) - int(m.group(1)) <= 10:
        return None
    street = normalize_street(m.group(3))
    if street.split()[-1].upper() not in STREET_SUFFIXES:
        street += " ST"
    hits = []
    for n in range(int(m.group(1)), int(m.group(2)) + 1):
        cache = CACHE / f"range_{r['address_id']}_{n}.json"
        if not cache.exists():
            resp = requests.get(f"{CENSUS}/onelineaddress", timeout=60, params={
                **PARAMS, "format": "json", "layers": "Incorporated Places,Counties",
                "address": f"{n} {street}, {r['postal_city']}, {r['state']}"})
            resp.raise_for_status()
            cache.write_text(json.dumps(resp.json()["result"]["addressMatches"]), encoding="utf-8")
        matches = json.loads(cache.read_text(encoding="utf-8"))
        exact = [x for x in matches if x["matchedAddress"].upper().startswith(f"{n} {street.upper()},")]
        if not matches:
            return None
        hits.extend(exact or matches)
    keys = set()
    for h in hits:
        g = h.get("geographies", {})
        keys.add((h["matchedAddress"].rsplit(",", 1)[-1].strip(),
                  (g.get("Incorporated Places") or [{}])[0].get("GEOID"), (g.get("Counties") or [{}])[0].get("GEOID")))
    if len(keys) != 1:
        return None
    h, g = hits[0], hits[0].get("geographies", {})
    place = (g.get("Incorporated Places") or [{}])[0]
    county = (g.get("Counties") or [{}])[0]
    return ("Match:range_consistent", h["matchedAddress"], h["coordinates"]["x"], h["coordinates"]["y"],
            (place.get("NAME"), place.get("GEOID"), county.get("NAME"), county.get("GEOID")))


def legal_city(place_name, state):
    """'Los Angeles city' -> 'Los Angeles, CA'. None when unincorporated."""
    if not place_name:
        return None
    name = re.sub(r"\s+(city|town|township|village|borough)$", "", place_name)
    return f"{name}, {state}"


def unit_bounds(r):
    """(min, max, source). Supplied `units` wins; else parse the use code / description."""
    desc, code, ds = r["use_description"].upper(), r["use_code"].upper(), r["source_dataset"]
    m = re.search(r"(\d+)\s*U\b|(\d+)U-", desc)              # NJ MOD-IV: '6B-20U-G' -> 20 units
    if r["units"].strip():
        n = int(float(r["units"]))
        if ds.startswith("NJOGIS") and m and int(m.group(1) or m.group(2)) != n:  # A0227: units=2 vs '93U'
            d = int(m.group(1) or m.group(2))
            return min(n, d), max(n, d), "conflict"           # keep both: engine answers 'unknown' in between
        return n, n, "supplied"
    if ds.startswith("NJOGIS") and m:
        n = int(m.group(1) or m.group(2))
        return n, n, "use_code"
    if ds.startswith("NJOGIS") and code == "4C":             # NJ class 4C = apartments, 5+ units
        return 5, None, "use_code"
    m = re.search(r"(\d+)\s*(?:TO|-)\s*(\d+)[- ]*UNIT", desc)  # 'Apartment 5 to 14 Units', 'APT 7-30 UNITS', '4-8-UNIT-APT'
    if m:
        return int(m.group(1)), int(m.group(2)), "use_code"
    m = re.search(r">\s*(\d+)[- ]*UNIT", desc)               # Cambridge '>8-UNIT-APT'
    if m:
        return int(m.group(1)) + 1, None, "use_code"
    m = re.search(r"(\d+)\s*(?:\+|UNITS? OR MORE)", desc)    # 'Apartment 15 Units or more', '(5+ units)'
    if m:
        return int(m.group(1)), None, "use_code"
    if "FIVE OR MORE" in desc:                               # LA 0500
        return 5, None, "use_code"
    return None, None, "unknown"


def fill_from_city(out):
    """Rows Census could not place (postal_fallback): copy city/county/state GEOIDs from the geocoded rows of
    the same legal city (only if they all agree), and use the supplied ZIP only for datasets whose ZIPs
    match Census on every geocoded row. lat/lon stay empty. Marked geocode_match '...:city_inferred'."""
    geo_by_city, zip_ok = collections.defaultdict(set), collections.defaultdict(set)
    for o in out:
        if o["legal_city_source"] != "postal_fallback":
            geo_by_city[o["legal_city"]].add((o["legal_city_geoid"], o["county"], o["county_geoid"]))
            if o["zip"] and o["zip_geocoded"]:
                zip_ok[o["source_dataset"]].add(o["zip"] == o["zip_geocoded"])
    for o in out:
        if o["legal_city_source"] != "postal_fallback" or len(geo_by_city[o["legal_city"]]) != 1:
            continue
        (o["legal_city_geoid"], o["county"], o["county_geoid"]), = geo_by_city[o["legal_city"]]
        o["state_geoid"] = o["county_geoid"][:2]
        if o["zip"] and zip_ok[o["source_dataset"]] == {True}:
            o["zip_geocoded"] = o["zip"]
        o["geocode_match"] += ":city_inferred"


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    geo = batch_geocode(rows)

    def enrich(r):
        match, matched, lon, lat = geo.get(r["address_id"], ("No_Match", "", None, None))
        place, source = (None, None, None, None), "census_batch"
        if lon is None:  # batch No_Match / Tie -> retry one by one
            match, matched, lon, lat, place = oneline(r)
            source = "census_oneline"
            if (match == "No_Match" or match.startswith("Tie")) and (ranged := range_fallback(r)):
                match, matched, lon, lat, place = ranged
                source = "census_range"
            elif match.startswith("Tie"):  # unresolved tie: drop the arbitrary first candidate's geography
                matched, lon, lat, place = "", None, None, (None, None, None, None)
        elif lon is not None:
            place = place_for(r["address_id"], lon, lat)
        city = legal_city(place[0], r["state"])
        if not city:  # last resort: postal city, Boston neighborhoods -> Boston; flagged as low confidence
            city = f"{'Boston' if r['state'] == 'MA' and r['postal_city'] in BOSTON_NEIGHBORHOODS else r['postal_city']}, {r['state']}"
            source = "postal_fallback"
        zip_geo = matched.rsplit(",", 1)[-1].strip() if matched else ""
        umin, umax, usrc = unit_bounds(r)
        return {**r,
                "legal_city": city, "legal_city_source": source,
                "legal_city_geoid": place[1] or "",
                "county": place[2] or "", "county_geoid": place[3] or "",
                "state_geoid": (place[3] or "")[:2],
                "zip_geocoded": zip_geo, "lat": lat or "", "lon": lon or "",
                "geocode_match": match,
                "units_min": umin if umin is not None else "", "units_max": umax if umax is not None else "",
                "units_source": usrc, "provenance": "supplied"}

    with ThreadPoolExecutor(8) as pool:
        out = list(pool.map(enrich, rows))
    fill_from_city(out)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    # Report
    n = len(out)
    print(f"{n} addresses -> {OUT.relative_to(ROOT)}")
    print("geocoded:", sum(o["geocode_match"].startswith("Match") for o in out), "/", n)
    print("legal city source:", dict(collections.Counter(o["legal_city_source"] for o in out)))
    print("postal city != legal city:", sum(bool(o["legal_city"]) and o["legal_city"].split(",")[0] != o["postal_city"] for o in out))
    print("units known: supplied", sum(o["units_source"] == "supplied" for o in out),
          "| from use code", sum(o["units_source"] == "use_code" for o in out),
          "| unknown", sum(o["units_source"] == "unknown" for o in out))


if __name__ == "__main__":
    main()
