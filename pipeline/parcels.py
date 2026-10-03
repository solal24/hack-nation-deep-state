"""Public parcel/assessor adapters, one per city: the same dataset the 500-address sample came from.

fetch(geo, cache) -> {parcel_id, zip, year_built, units, use_code, use_description, source_url, match}
`geo` comes from online_address.geocode (number, street_name, suffix, zip, lat, lon, legal_city).
A parcel is accepted only if its house number AND street name match the geocoded address: never "nearest
parcel", so we can't silently report a neighbour's building. Missing facts stay "" (the engine turns them
into "unknown"); never guessed.
"""
import collections
import re

import requests


def _url(base, params):
    return requests.Request("GET", base, params=params).prepare().url


def _num(s):
    m = re.match(r"\d+", str(s))
    return int(m.group()) if m else None


def _house_range(text):
    """'69-71' -> (69, 71), '322-322.5' -> (322, 322), '33' -> (33, 33)."""
    nums = [int(float(n)) for n in re.findall(r"\d+(?:\.\d+)?", text)[:2]]
    if not nums:
        return None
    lo, hi = min(nums), max(nums)
    return (lo, hi) if hi - lo < 100 else (nums[0], nums[0])


def _tokens(text):
    """Upper-case words with leading zeros stripped ('05TH' -> '5TH')."""
    return {re.sub(r"^0+(?=\w)", "", t) for t in re.sub(r"[^A-Z0-9 ]", " ", text.upper()).split()}


def _street_ok(geo, text):
    return _tokens(geo["street_name"]) <= _tokens(text)


SUFFIX_ALIASES = {"AVE": {"AVE", "AV"}, "ST": {"ST"}, "PL": {"PL"}, "RD": {"RD"}, "CT": {"CT"}, "TER": {"TER"}}


def _suffix_ok(geo, text):
    """'BOWDOIN ST' must not match 'BOWDOIN AV'. Passes when either side has no suffix we know."""
    want = SUFFIX_ALIASES.get(geo.get("suffix", ""))
    toks = _tokens(text)
    known = set().union(*SUFFIX_ALIASES.values()) & toks
    return not want or not known or bool(want & toks)


def _house_ok(geo, lo_hi):
    """Number inside the range, on the same side of the street (19-23 covers 19, 21, 23, never 22)."""
    n = _num(geo["number"])
    return lo_hi is not None and n is not None and lo_hi[0] <= n <= lo_hi[1] and (n - lo_hi[0]) % 2 == 0


def _exact_first(geo, hits, rng):
    """Prefer records whose number is exactly the geocoded one over records that merely cover it in a range."""
    n = _num(geo["number"])
    exact = [h for h in hits if rng(h) == (n, n)]
    return exact or hits


def _clean(v):
    """Assessor placeholders ('0', '0.0', None) -> ''."""
    if v is None:
        return ""
    v = str(v).strip()
    return "" if v in ("0", "0.0", "None") else re.sub(r"\.0$", "", v)


def _most_common(values):
    values = [v for v in values if v not in (None, "")]
    return collections.Counter(values).most_common(1)[0][0] if values else ""


def _year(v):
    """Year built, or '' for placeholders (NJ uses 0 and 1 for 'unknown')."""
    v = _clean(v)
    return v if v.isdigit() and 1700 <= int(v) <= 2100 else ""


# ---------- San Francisco · DataSF Assessor Secured Property Tax Roll (wv5m-vpq2), Socrata ----------
SF_URL = "https://data.sf.gov/resource/wv5m-vpq2.json"
SF_FIELDS = ("parcel_number,property_location,year_property_built,number_of_units,"
             "property_class_code,property_class_code_definition")


def _sf_range(loc):
    """'0000 3515 FILLMORE             ST0000' -> (3515, 3515); '3149 3145 MISSION ...' -> (3145, 3149)."""
    nums = [n for n in (_num(loc[:4]), _num(loc[5:9])) if n]
    return (min(nums), max(nums)) if nums else None


def sf(geo, cache):
    params = {"$select": SF_FIELDS, "$limit": 200,
              "$where": f"closed_roll_year=2025 AND within_circle(the_geom, {geo['lat']}, {geo['lon']}, 80)"}
    rows = cache(SF_URL, params, "sf")
    hits = [r for r in rows if _house_ok(geo, _sf_range(r["property_location"]))
            and _street_ok(geo, r["property_location"][10:-4])]
    if not hits:  # the Census point can sit far from the parcel point on long blocks: try the address itself
        params["$where"] = (f"closed_roll_year=2025 AND property_location like "
                            f"'%{int(_num(geo['number'])):04d}%{geo['street_name'].split()[0]}%'")
        rows = cache(SF_URL, params, "sf_addr")
        hits = [r for r in rows if _house_ok(geo, _sf_range(r["property_location"]))
                and _street_ok(geo, r["property_location"][10:-4])]
    hits = _exact_first(geo, hits, lambda r: _sf_range(r["property_location"]))
    if not hits:
        return {"match": "no_parcel_found", "source_url": _url(SF_URL, params)}
    # Condos are one parcel per unit at the same address (unit suffix differs): sum their units.
    base = max(hits, key=lambda r: float(r.get("number_of_units") or 0))
    same_building = len({r["property_location"][:-4] for r in hits}) == 1
    units = sum(float(r.get("number_of_units") or 0) for r in hits) if len(hits) > 1 and same_building         else base.get("number_of_units")
    return {"parcel_id": base["parcel_number"], "year_built": _year(base.get("year_property_built")),
            "units": _clean(units), "use_code": base.get("property_class_code", ""),
            "use_description": base.get("property_class_code_definition", ""),
            "source_url": _url(SF_URL, params),
            "match": "address" if len(hits) == 1 else
            f"address_{len(hits)}_{'condo_parcels_units_summed' if same_building else 'parcels_largest_kept'}"}


# ---------- Boston · Property Assessment FY2026, CKAN (no coordinates: match by address) ----------
BOS_URL = "https://data.boston.gov/api/3/action/datastore_search_sql"
BOS_RESOURCE = "ee73430d-96c0-423e-ad21-c4cfb54c8961"
BOS_FAMILY_UNITS = {"R1": "1", "R2": "2", "R3": "3"}   # one-, two-, three-family dwellings: units by definition


def boston(geo, cache):
    name = re.sub(r"[^A-Z0-9 ]", "", geo["street_name"])   # also keeps the SQL safe
    zip5 = re.sub(r"\D", "", geo["zip"])[:5]
    select = (f'SELECT "PID","ST_NUM","ST_NUM2","ST_NAME","UNIT_NUM","ZIP_CODE","LU","LUC","LU_DESC",'
              f'"YR_BUILT","RES_UNITS","BLDG_SEQ" FROM "{BOS_RESOURCE}" WHERE upper("ST_NAME") LIKE \'{name} %\'')
    params = {"sql": f"{select} AND \"ZIP_CODE\" = '{zip5}' LIMIT 3000"}
    rows = cache(BOS_URL, params, "boston")["result"]["records"]
    rng = lambda r: _house_range(f"{r['ST_NUM']}-{r['ST_NUM2'] or r['ST_NUM']}")
    keep = lambda rs: _exact_first(geo, [r for r in rs if _house_ok(geo, rng(r)) and _street_ok(geo, r["ST_NAME"])
                                         and _suffix_ok(geo, r["ST_NAME"])], rng)
    hits = keep(rows)
    if not hits:  # Census ZIP and assessor ZIP can disagree (50 Bowdoin St: 02124 vs 02121): drop the ZIP filter,
        n = _num(geo["number"])                                             # accept only an unambiguous ZIP
        params = {"sql": f"{select} AND (\"ST_NUM\" = '{n}' OR \"ST_NUM2\" IS NOT NULL) LIMIT 3000"}
        hits = keep(cache(BOS_URL, params, "boston_nozip")["result"]["records"])
        if len({r["ZIP_CODE"] for r in hits}) != 1:
            hits = []
    whole = [r for r in hits if not r.get("UNIT_NUM") and r["LU"] != "CD"]  # skip per-unit condo rows
    if not whole:
        return {"match": "no_parcel_found", "source_url": _url(BOS_URL, params)}
    r = sorted(whole, key=lambda r: (r["LU"] != "CM", str(r.get("BLDG_SEQ") or "")))[0]
    return {"parcel_id": r["PID"], "zip": r["ZIP_CODE"], "year_built": _year(r["YR_BUILT"]),
            "units": _clean(r["RES_UNITS"]) or BOS_FAMILY_UNITS.get(r["LU"], ""), "use_code": f"{r['LU']}/{r['LUC']}",
            "use_description": r["LU_DESC"] or "", "source_url": _url(BOS_URL, params),
            "match": "address" if len(whole) == 1 else f"address_{len(whole)}_rows_first_building"}


# ---------- Cambridge · Property Database FY2026 (waa7-ibdu), Socrata ----------
CAM_URL = "https://data.cambridgema.gov/resource/waa7-ibdu.json"


def cambridge(geo, cache):
    name = re.sub(r"[^A-Z0-9 ]", "", geo["street_name"])
    params = {"$select": "pid,address,stateclasscode,propertyclass,condition_yearbuilt,interior_numunits,bldgnum",
              "$where": f"upper(address) like '%{name}%' AND upper(address) like '%{_num(geo['number'])}%'",
              "$limit": 200}
    rows = cache(CAM_URL, params, "cambridge")
    rng = lambda r: _house_range(r["address"].split()[0])
    hits = _exact_first(geo, [r for r in rows if _house_ok(geo, rng(r)) and _street_ok(geo, r["address"])], rng)
    if not hits:
        return {"match": "no_parcel_found", "source_url": _url(CAM_URL, params)}
    r = sorted(hits, key=lambda r: str(r.get("bldgnum") or ""))[0]
    return {"parcel_id": r["pid"], "year_built": _year(r.get("condition_yearbuilt")),
            "units": _clean(r.get("interior_numunits")), "use_code": r.get("stateclasscode", ""),
            "use_description": r.get("propertyclass", ""), "source_url": _url(CAM_URL, params),
            "match": "address" if len(hits) == 1 else f"address_{len(hits)}_rows_first_building"}


# ---------- New Jersey · NJOGIS Parcels & MOD-IV Composite, ArcGIS (Jersey City, Hoboken, Newark) ----------
NJ_URL = ("https://services2.arcgis.com/XVOqAjTOJ5P6ngMu/arcgis/rest/services/"
          "Parcels_Composite_NJ_WM/FeatureServer/0/query")
NJ_FIELDS = "PAMS_PIN,MUN_NAME,PROP_LOC,PROP_CLASS,BLDG_DESC,YR_CONSTR"
# ZIP5/CITY_STATE in this layer are the OWNER's mailing address: never used. Units come from BLDG_DESC
# ('6B-20U-G' -> 20) in enrich.unit_bounds, exactly like the sample; DWELL is unreliable.


def nj(geo, cache):
    mun = geo["legal_city"].split(",")[0].upper()
    params = {"geometry": f"{geo['lon']},{geo['lat']}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "distance": 60, "units": "esriSRUnit_Meter",
              "where": f"MUN_NAME LIKE '{mun}%'", "outFields": NJ_FIELDS, "returnGeometry": "false", "f": "json"}
    feats = cache(NJ_URL, params, "nj")["features"]
    hits = [f["attributes"] for f in feats if f["attributes"].get("PROP_LOC")
            and _house_ok(geo, _house_range(f["attributes"]["PROP_LOC"].split()[0]))
            and _street_ok(geo, f["attributes"]["PROP_LOC"])]
    if not hits:  # geocoded point can be ~100 m off: search the address within the municipality
        name = re.sub(r"[^A-Z0-9 ]", "", geo["street_name"])
        params = {"where": f"MUN_NAME LIKE '{mun}%' AND PROP_LOC LIKE '%{_num(geo['number'])}%{name}%'",
                  "outFields": NJ_FIELDS, "returnGeometry": "false", "f": "json"}
        feats = cache(NJ_URL, params, "nj_addr")["features"]
        hits = [f["attributes"] for f in feats if _street_ok(geo, f["attributes"]["PROP_LOC"])
                and _house_ok(geo, _house_range(f["attributes"]["PROP_LOC"].split()[0]))]
    hits = _exact_first(geo, hits, lambda a: _house_range(a["PROP_LOC"].split()[0]))
    if not hits:
        return {"match": "no_parcel_found", "source_url": _url(NJ_URL, params)}
    # Condo units are stacked records (class 2); prefer the building-level record (4C apartments first).
    r = sorted(hits, key=lambda a: (a.get("PROP_CLASS") != "4C", a.get("PROP_CLASS") == "2"))[0]
    return {"parcel_id": r["PAMS_PIN"], "year_built": _year(r.get("YR_CONSTR")), "units": "",
            "use_code": r.get("PROP_CLASS") or "", "use_description": r.get("BLDG_DESC") or "",
            "source_url": _url(NJ_URL, params),
            "match": "address" if len(hits) == 1 else f"address_{len(hits)}_records_building_level"}


# ---------- ArcGIS helper: buffered point query, then address query (Census points sit off the parcel) ----------
def _arcgis(url, geo, cache, tag, fields, where_area, where_addr, loc, rng):
    """Return (hits, params). `loc(attrs)` -> address text for the street check, `rng(attrs)` -> house range."""
    def ok(a):
        return loc(a) and _house_ok(geo, rng(a)) and _street_ok(geo, loc(a))
    params = {"geometry": f"{geo['lon']},{geo['lat']}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "distance": 60, "units": "esriSRUnit_Meter",
              "where": where_area, "outFields": fields, "returnGeometry": "false", "f": "json"}
    hits = [f["attributes"] for f in cache(url, params, tag).get("features", []) if ok(f["attributes"])]
    if not hits:
        params = {"where": f"{where_area} AND {where_addr}", "outFields": fields, "returnGeometry": "false", "f": "json"}
        hits = [f["attributes"] for f in cache(url, params, f"{tag}_addr").get("features", []) if ok(f["attributes"])]
    return _exact_first(geo, hits, rng), params


def _sql_name(geo):
    return re.sub(r"[^A-Z0-9 ]", "", geo["street_name"])


# ---------- Los Angeles · LA County Assessor parcels (eGIS), ArcGIS ----------
LA_URL = "https://public.gis.lacounty.gov/public/rest/services/LACounty_Cache/LACounty_Parcel/MapServer/0/query"


def la(geo, cache):
    hits, params = _arcgis(
        LA_URL, geo, cache, "la",
        "AIN,SitusHouseNo,SitusStreet,SitusUnit,SitusZIP,YearBuilt1,Units1,Units2,Units3,Units4,Units5,UseCode,UseDescription",
        "SitusCity LIKE 'LOS ANGELES%'",
        f"SitusHouseNo = '{_num(geo['number'])}' AND SitusStreet LIKE '%{_sql_name(geo)}%'",
        loc=lambda a: a.get("SitusStreet") or "", rng=lambda a: _house_range(a.get("SitusHouseNo") or ""))
    if not hits:
        return {"match": "no_parcel_found", "source_url": _url(LA_URL, params)}
    # One record per parcel; a condo tower is one parcel per unit at the same address -> aggregate them.
    units = sum(sum(a.get(f"Units{i}") or 0 for i in range(1, 6)) for a in hits)   # up to 5 buildings per parcel
    use = _most_common(a.get("UseCode") for a in hits)
    r = next(a for a in hits if a.get("UseCode") == use)
    return {"parcel_id": r["AIN"], "zip": (r.get("SitusZIP") or "")[:5],
            "year_built": _year(_most_common(a.get("YearBuilt1") for a in hits)),
            "units": _clean(units), "use_code": use, "use_description": r.get("UseDescription") or "",
            "source_url": _url(LA_URL, params),
            "match": "address" if len(hits) == 1 else f"address_{len(hits)}_parcels_aggregated"}


# ---------- San Diego · SANDAG/SanGIS parcels, ArcGIS (no year built in this dataset) ----------
SD_URL = "https://geo.sandag.org/server/rest/services/Hosted/Parcels/FeatureServer/0/query"


def sd(geo, cache):
    hits, params = _arcgis(
        SD_URL, geo, cache, "sd", "apn,situs_address,situs_street,situs_suffix,situs_zip,asr_landuse,unitqty",
        "situs_juris = 'SD'",
        f"situs_address = {_num(geo['number'])} AND situs_street LIKE '%{_sql_name(geo)}%'",
        loc=lambda a: f"{a.get('situs_street') or ''} {a.get('situs_suffix') or ''}",
        rng=lambda a: _house_range(str(a.get("situs_address") or "")))
    if not hits:
        return {"match": "no_parcel_found", "source_url": _url(SD_URL, params)}
    r = hits[0]
    code = _most_common(a.get("asr_landuse") for a in hits)
    desc = "SANDAG asr_landuse 14-16 (5+ units)" if code in (14, 15, 16) else f"SANDAG asr_landuse {code}"
    return {"parcel_id": r["apn"], "zip": (r.get("situs_zip") or "")[:5], "year_built": "",
            "units": _clean(sum(a.get("unitqty") or 0 for a in hits)), "use_code": str(code),
            "use_description": desc, "source_url": _url(SD_URL, params),
            "match": "address" if len(hits) == 1 else f"address_{len(hits)}_parcels_aggregated"}


# ---------- Berkeley · Alameda County Assessor parcels, ArcGIS (use code only: no year, no units) ----------
ALA_URL = "https://services5.arcgis.com/ROBnTHSNjoZ2Wm1P/arcgis/rest/services/Parcels/FeatureServer/0/query"


def berkeley(geo, cache):
    hits, params = _arcgis(
        ALA_URL, geo, cache, "berkeley", "APN,SitusStreetNumber,SitusStreetName,SitusUnit,SitusZip,UseCode",
        "SitusCity = 'BERKELEY'",
        f"SitusStreetNumber = '{_num(geo['number'])}' AND SitusStreetName LIKE '%{_sql_name(geo)}%'",
        loc=lambda a: a.get("SitusStreetName") or "", rng=lambda a: _house_range(a.get("SitusStreetNumber") or ""))
    if not hits:
        return {"match": "no_parcel_found", "source_url": _url(ALA_URL, params)}
    code = str(_most_common((a.get("UseCode") or "").strip() for a in hits))
    r = next(a for a in hits if (a.get("UseCode") or "").strip() == code)
    desc = "Alameda County use code (5+ units)" if code in ("7200", "7700") else f"Alameda County use code {code}"
    return {"parcel_id": r["APN"], "zip": (r.get("SitusZip") or "")[:5], "year_built": "", "units": "",
            "use_code": code, "use_description": desc, "source_url": _url(ALA_URL, params),
            "match": "address" if len(hits) == 1 else f"address_{len(hits)}_parcels_most_common_use"}


# legal city -> source dataset name (exactly as in starter/data/sample_addresses.csv) + adapter
SOURCES = {
    "Los Angeles, CA":   {"dataset": "LA County eGIS parcels", "fetch": la},
    "San Francisco, CA": {"dataset": "DataSF wv5m-vpq2 (2025 roll)", "fetch": sf},
    "San Diego, CA":     {"dataset": "SANDAG/SanGIS parcels", "fetch": sd},
    "Berkeley, CA":      {"dataset": "Alameda County parcels", "fetch": berkeley},
    "Jersey City, NJ":   {"dataset": "NJOGIS Parcels & MOD-IV Composite", "fetch": nj},
    "Hoboken, NJ":       {"dataset": "NJOGIS Parcels & MOD-IV Composite", "fetch": nj},
    "Newark, NJ":        {"dataset": "NJOGIS Parcels & MOD-IV Composite", "fetch": nj},
    "Boston, MA":        {"dataset": "Boston Property Assessment FY2026", "fetch": boston},
    "Cambridge, MA":     {"dataset": "Cambridge Property Database FY2026 (waa7-ibdu)", "fetch": cambridge},
}


def fetch(geo, cache):
    adapter = SOURCES[geo["legal_city"]].get("fetch")
    if adapter is None:
        return {"match": "no_adapter_yet"}
    return adapter(geo, cache)
