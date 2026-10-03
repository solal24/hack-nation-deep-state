"""External data · official law texts found by hand on government sites -> corpus_extra/ (CLAUDE.md hand-off).

Each document below was located manually on the issuing government's own site (city clerk portal, state site,
court) and is fetched once, one page at a time (no crawling), cached in data/cache/external/. The text is
extracted as-is (PDF pages joined in order, nothing summarized or rewritten) and written to
corpus_extra/text/<doc_id>.txt with the SOURCE / RETRIEVED header, plus one row in corpus_extra/manifest.csv
(provenance "elie_manual"). Rules extracted from these land in outputs/rules_all.json with review_status
"to_review"; outputs/rules.json stays supplied-corpus-only unless organizers allow outside sources.

A site that refuses scripts (mass.gov answers 403) is not worked around: download that file in a browser,
save it as data/cache/external/official_<doc_id>.bin and re-run; the copy is then used as the source.

Run: python -m pipeline.official_texts            (all documents)
     python -m pipeline.official_texts X004       (one)
"""
import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from pypdf import PdfReader

from pipeline.bill_texts import COLUMNS, html_to_text

ROOT = Path(__file__).resolve().parent.parent
EXTRA = ROOT / "corpus_extra"
MANIFEST = EXTRA / "manifest.csv"
CACHE = ROOT / "data/cache/external"

DOCS = {
    # X004 (Jersey City Ord. 25-057) and X005 (Hoboken Ord. B-781) are Solal's captures (provenance
    # manual_official), already ingested: not re-fetched here, so their text and LLM cache stay identical.
    "X006": {
        "url": "https://www.mass.gov/doc/25-21-an-initiative-petition-to-protect-tenants-by-limiting-rent-increases/download",
        "found_via": "mass.gov (Attorney General) > Ballot initiatives submitted for the 2026 statewide election > 25-21",
        "jurisdictions": "MA",
        "bill": "Initiative Petition 25-21, 'An Initiative Petition to Protect Tenants by Limiting Rent Increases'",
        "bill_status": "failed: struck from the 2026 ballot by the SJC on 2026-06-23 (Cella v. Attorney General, "
                       "SJC-13893, see X007); never law",
        "bill_dates": "2025 filed with and certified by the Attorney General; 2026-06-23 SJC: not in compliance with "
                      "art. 48 excluded matters, Secretary enjoined from placing it on the ballot",
        "change_tests": "T5",
    },
    "X007": {
        "url": "https://www.ma-appellatecourts.org/docket/SJC-13893",
        "found_via": "Massachusetts Appellate Courts public case search, docket SJC-13893 (official court record); "
                     "saved by hand from a browser as PDF because the site answers 403 to scripts. The mass.gov "
                     "slip-opinion link did not work",
        "jurisdictions": "MA",
        "bill": "Cella v. Attorney General, SJC-13893, 497 Mass. 706 (decided 2026-06-23): docket incl. rescript",
        "bill_status": "court decision: IP 25-21 contains excluded matters (art. 48); Secretary enjoined from placing "
                       "it on the 2026 ballot -> petition failed",
        "bill_dates": "2026-02-18 entered; 2026-05-06 argued; 2026-06-23 decided (rescript, full opinion); "
                      "2026-07-21 rescript issued to trial court",
        "change_tests": "T5",
    },
    # Newark: the attached PDFs are scans (no text layer); Legistar stores the ordinance text itself.
    # The supplied corpus has no Newark text at all (D070-D072 are ecode360, check-terms).
    "X010": {
        "url": "https://webapi.legistar.com/v1/newark/matters/1608659/texts/1555618",
        "json_field": "MatterTextPlain",
        "found_via": "Newark Legistar matter 24-1160 (https://newark.legistar.com, LegislationDetail ID=1608659), "
                     "stored matter text, version 1; the certified ordinance PDF attachment is the signed copy",
        "jurisdictions": "Newark, NJ",
        "bill": "Newark ordinance 24-1160 amending 6PSF-I: Title XIX Rent Control, Chapter 2 (Rent Control "
                "Regulations; Rent Control Board), full chapter text incl. § 19:2-3 rent increases (CPI, max 4%)",
        "bill_status": "adopted 2024-09-18 (Legistar status 'Adopted'); later amended by 26-0532 (X008)",
        "bill_dates": "2024-08-15 introduced; 2024-09-18 adopted",
    },
    "X008": {
        "url": "https://webapi.legistar.com/v1/newark/matters/1611524/texts/1559191",
        "json_field": "MatterTextPlain",
        "found_via": "Newark Legistar matter 26-0532 (https://newark.legistar.com/LegislationDetail.aspx?ID=1611524"
                     "&GUID=2864F5C6-2BDC-4A7B-A1EC-A99FF0E3D674), stored matter text, version 1",
        "jurisdictions": "Newark, NJ",
        "bill": "Newark ordinance 26-0532, amending Ord. 6PSF-I, Title XIX Rent Control, Chapter 2 (Rent Control "
                "Regulations; Rent Control Board)",
        "bill_status": "adopted 2026-05-20 (Legistar status 'Adopted'; only one text version is stored)",
        "bill_dates": "2026-04-08 introduced; 2026-05-20 adopted",
    },
    "X009": {
        "url": "https://webapi.legistar.com/v1/newark/matters/1611507/texts/1559171",
        "json_field": "MatterTextPlain",
        "found_via": "Newark Legistar matter 26-0515 (stored matter text, version 1); certified ordinance PDF is a scan",
        "jurisdictions": "Newark, NJ",
        "bill": "Newark ordinance 26-0515, amending Title XIX, Chapter 19:3 (Rent Control), legal services in "
                "eviction proceedings: definition of income-eligible individual",
        "bill_status": "adopted 2026-05-20 (Legistar status 'Adopted'; certified ordinance attached as a scan)",
        "bill_dates": "2026-04-07 introduced; 2026-05-20 adopted",
    },
}


def fetch(doc_id, url):
    """One GET per document, cached (the cache is the audit copy of exactly what was read)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"official_{doc_id}.bin"
    if not path.exists():
        r = requests.get(url, timeout=120, headers={"User-Agent": "hack-nation-deep-state research (one-off fetch)"})
        r.raise_for_status()
        path.write_bytes(r.content)
    fetched = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)   # when it was really downloaded
    return path.read_bytes(), fetched


def to_text(raw, json_field=None):
    if json_field:   # e.g. Legistar matter text: the city's own stored text of the ordinance, taken verbatim
        return json.loads(raw)[json_field].replace("\r\n", "\n").strip(), "json"
    if raw[:5] == b"%PDF-":
        pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages]
        if sum(len(p.strip()) for p in pages) < 200:
            raise ValueError("PDF has no text layer (scanned image): needs OCR, not handled automatically")
        return "\n\n".join(p.rstrip() for p in pages), "pdf"
    return html_to_text(raw.decode("utf-8", errors="replace")), "html"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("doc_ids", nargs="*", help="only these (default: all)")
    args = ap.parse_args()
    rows = {r["doc_id"]: r for r in csv.DictReader(MANIFEST.open(encoding="utf-8"))} if MANIFEST.exists() else {}
    (EXTRA / "text").mkdir(parents=True, exist_ok=True)
    for doc_id, d in DOCS.items():
        if args.doc_ids and doc_id not in args.doc_ids:
            continue
        try:
            raw, now = fetch(doc_id, d["url"])
            text, kind = to_text(raw, d.get("json_field"))
        except (requests.HTTPError, ValueError) as e:
            # e.g. mass.gov answers 403 to scripts: we don't work around it. Download the file in a browser and
            # save it as data/cache/external/official_<doc_id>.bin, then re-run (fetch() uses that copy).
            print(f"  {doc_id} SKIPPED ({e}). Save it by hand as {CACHE.relative_to(ROOT)}/official_{doc_id}.bin")
            continue
        path = EXTRA / "text" / f"{doc_id}.txt"
        path.write_text(f"SOURCE: {d['url']}\nRETRIEVED: {now:%Y-%m-%d %H:%M} UTC\n\n{text}\n", encoding="utf-8")
        rows[doc_id] = {"doc_id": doc_id, "jurisdictions": d["jurisdictions"], "url": d["url"],
                        "source_type": "official", "capture": "yes", "retrieved_at": f"{now:%Y-%m-%dT%H:%MZ}",
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "text_file": f"text/{doc_id}.txt",
                        "status": "ok", "provenance": "elie_manual", "bill": d["bill"],
                        "bill_status": d["bill_status"], "bill_dates": d["bill_dates"],
                        "effective_clause_verbatim": d.get("effective_clause", "not stated in text")}
        print(f"  {doc_id} {d['jurisdictions']:16} {kind} {len(raw):7} bytes -> {len(text):6} chars · {d['bill']}")
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["doc_id"]))
    print(f"{len(rows)} documents in {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
