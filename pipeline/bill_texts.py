"""External data · official texts of enacted bills (supplemental corpus, separate from the supplied one).

For every bill in data/external/bills.json with status "enacted", fetch its final version (Chaptered /
Enrolled / Approved) through LegiScan getBillText (CC BY 4.0; the document is the state legislature's own
text) and save it in the same shape as starter/corpus/text: a header with source URL and retrieval date,
then plain text. Manifest: data/external/texts_manifest.csv (doc_id X###, sha256, ...), like the supplied
corpus_manifest.csv, so pipeline.extract could ingest these docs IF the organizers allow supplemental
sources. Until then they are reference only (provenance="public").
Also records each act's own effective-date sentence, quoted verbatim, or "not stated in text".

Run: python -m pipeline.bill_texts
"""
import base64
import csv
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from pipeline.legislation import legiscan

ROOT = Path(__file__).resolve().parent.parent
BILLS = ROOT / "data/external/bills.json"
TEXT_DIR = ROOT / "data/external/texts"
MANIFEST = ROOT / "data/external/texts_manifest.csv"
FINAL = ["Chaptered", "Approved", "Enrolled", "Enacted"]   # preferred version, in order


class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table", "section"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw):
    p = _Text()
    p.feed(raw)
    text = html.unescape("".join(p.parts)).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def effective_clause(text):
    """The act's own 'take(s) effect' sentence, verbatim (whitespace-normalized), or None."""
    flat = re.sub(r"\s+", " ", text)
    hits = re.findall(r"[^.]*\b(?:shall take effect|takes effect|shall become operative|is operative)\b[^.]*\.", flat, re.I)
    return hits[-1].strip() if hits else None


def main():
    bills = [b for b in json.loads(BILLS.read_text(encoding="utf-8")) if b["status"] == "enacted"]
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    rows = []
    for i, b in enumerate(sorted(bills, key=lambda b: b["bill_key"]), 1):
        texts = sorted(b["texts"], key=lambda t: (FINAL.index(t["type"]) if t["type"] in FINAL else 99, t["date"]))
        t = texts[0]
        doc = legiscan("getBillText", id=t["legiscan_doc_id"])["text"]
        raw = base64.b64decode(doc["doc"])
        if "html" not in doc["mime"]:
            print(f"  skip {b['bill_key']}: {doc['mime']} (only HTML texts are converted)")
            continue
        body = html_to_text(raw.decode("utf-8", errors="replace"))
        doc_id = f"X{i:03d}"
        header = (f"Source: {t['state_link'] or doc.get('state_link')}\nRetrieved: {now}\n"
                  f"Via: LegiScan getBillText doc {t['legiscan_doc_id']} (CC BY 4.0) · version: {t['type']} {t['date']}\n"
                  f"Provenance: public (not part of the supplied corpus)\n\n")
        path = TEXT_DIR / f"{doc_id}_{b['bill_key']}.txt"
        path.write_text(header + body, encoding="utf-8")
        clause = effective_clause(body)
        rows.append({"doc_id": doc_id, "bill_key": b["bill_key"], "jurisdictions": b["jurisdiction"],
                     "title": b["title"], "url": t["state_link"], "source_type": "official (bill text via LegiScan)",
                     "version": f"{t['type']} {t['date']}", "retrieved_at": now,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "text_file": f"texts/{path.name}", "categories": ";".join(b["categories"]),
                     "change_tests": ";".join(b["change_tests"]),
                     "also_in_supplied_corpus": ";".join(b["in_supplied_corpus"]),
                     "effective_clause_verbatim": clause or "not stated in text", "provenance": "public",
                     "review_status": "unreviewed"})
        print(f"  {doc_id} {b['bill_key']:10} {t['type']:9} {len(body):7} chars · effective: {(clause or 'not stated in text')[:110]}")
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} texts -> {TEXT_DIR.relative_to(ROOT)}, {MANIFEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
