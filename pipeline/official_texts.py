"""External data · official law texts found by hand on government sites -> corpus_extra/ (CLAUDE.md hand-off).

Each document below was located manually on the issuing government's own site (city clerk portal, state site,
court) and is fetched once, one page at a time (no crawling), cached in data/cache/external/. The text is
extracted as-is (PDF pages joined in order, nothing summarized or rewritten) and written to
corpus_extra/text/<doc_id>.txt with the SOURCE / RETRIEVED header, plus one row in corpus_extra/manifest.csv
(provenance "elie_manual"). Rules extracted from these land in outputs/rules_all.json with review_status
"to_review"; outputs/rules.json stays supplied-corpus-only unless organizers allow outside sources.

Run: python -m pipeline.official_texts            (all documents)
     python -m pipeline.official_texts X004       (one)
"""
import argparse
import csv
import hashlib
import io
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
    "X004": {
        "url": "https://cityofjerseycity.civicweb.net/document/429156",
        "found_via": "jerseycitynj.gov > City Clerk > Ordinances & Resolutions (2019-Present) > 2025 > May 21, 2025",
        "jurisdictions": "Jersey City, NJ",
        "bill": "Jersey City Ord. 25-057 (Code ch. 218, new § 218-12)",
        "bill_status": "adopted (final passage 2025-05-21, 9-0; approved by mayor 2025-05-22)",
        "bill_dates": "2025-05-07 introduced (first reading, 8-0); 2025-05-21 adopted on second and final reading (9-0); "
                      "2025-05-22 approved by mayor",
        "change_tests": "T2, T3",
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
    return path.read_bytes()


def to_text(raw):
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
        raw = fetch(doc_id, d["url"])
        text, kind = to_text(raw)
        now = datetime.now(timezone.utc)
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
