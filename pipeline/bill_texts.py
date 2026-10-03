"""External data · official texts of enacted bills -> corpus_extra/ (Solal's hand-off, see CLAUDE.md).

For every bill in data/external/bills.json with status "enacted", fetch its final version (Chaptered /
Enrolled) through LegiScan getBillText (CC BY 4.0; the document is the legislature's own text) and write
corpus_extra/text/X###.txt (SOURCE / RETRIEVED header, full text, no rewriting) + one row in
corpus_extra/manifest.csv (starter manifest columns + provenance=legiscan_api + bill status and dates).
Bills whose official text is already in the supplied corpus (e.g. AB 325 = D022, NJ FAIR Act = D069) are
skipped. Each act's own effective-date sentence is recorded verbatim, or "not stated in text".
Then: make ingest DOC=X001,... (rules land in outputs/rules_all.json with review_status "to_review";
outputs/rules.json stays RealPage-only unless SOURCES=all).

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
EXTRA = ROOT / "corpus_extra"
MANIFEST = EXTRA / "manifest.csv"
SUPPLIED = ROOT / "starter/corpus/text"
COLUMNS = ["doc_id", "jurisdictions", "url", "source_type", "capture", "retrieved_at", "sha256", "text_file",
           "status", "provenance", "bill", "bill_status", "bill_dates", "effective_clause_verbatim"]
FINAL = ["Chaptered", "Approved", "Enrolled", "Enacted"]   # preferred version, in order
PROGRESS = {1: "introduced", 2: "engrossed", 3: "enrolled", 4: "passed", 5: "vetoed", 6: "failed"}


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


def _doc_key(url):
    """Same document across hosts: CA bill_id, else lower-case path (njleg.gov == njleg.state.nj.us)."""
    m = re.search(r"bill_id=(\w+)", url or "")
    return m.group(1) if m else re.sub(r"^https?://[^/]+", "", (url or "").split("#")[0]).lower()


def supplied_keys():
    keys = set()
    for f in SUPPLIED.glob("*.txt"):
        first = f.read_text(encoding="utf-8", errors="ignore").split("\n", 1)[0]
        if first.startswith("SOURCE:"):
            keys.add(_doc_key(first[len("SOURCE:"):].strip()))
    return keys


def main():
    bills = [b for b in json.loads(BILLS.read_text(encoding="utf-8")) if b["status"] == "enacted"]
    (EXTRA / "text").mkdir(parents=True, exist_ok=True)
    existing = list(csv.DictReader(MANIFEST.open(encoding="utf-8"))) if MANIFEST.exists() else []
    rows = {r["doc_id"]: r for r in existing}
    ours = {r.get("bill"): r["doc_id"] for r in existing if r.get("provenance") == "legiscan_api"}
    supplied = supplied_keys()
    now = datetime.now(timezone.utc)
    for b in sorted(bills, key=lambda b: b["bill_key"]):
        texts = sorted(b["texts"], key=lambda t: (FINAL.index(t["type"]) if t["type"] in FINAL else 99, t["date"]))
        t = texts[0]
        if _doc_key(t["state_link"]) in supplied or _doc_key(b["official_url"]) in supplied:
            print(f"  skip {b['bill_key']:10} official text already in the supplied corpus ({', '.join(b['in_supplied_corpus'])})")
            continue
        doc = legiscan("getBillText", id=t["legiscan_doc_id"])["text"]
        if "html" not in doc["mime"]:
            print(f"  skip {b['bill_key']:10} {doc['mime']} (only HTML texts are converted)")
            continue
        body = html_to_text(base64.b64decode(doc["doc"]).decode("utf-8", errors="replace"))
        doc_id = ours.get(b["bill_key"]) or f"X{len(rows) + 1:03d}"
        path = EXTRA / "text" / f"{doc_id}.txt"
        path.write_text(f"SOURCE: {t['state_link']}\nRETRIEVED: {now:%Y-%m-%d %H:%M} UTC\n\n{body}\n", encoding="utf-8")
        clause = effective_clause(body)
        dates = "; ".join(f"{p['date']} {PROGRESS.get(p['event'], p['event'])}" for p in b["progress"])
        rows[doc_id] = {"doc_id": doc_id, "jurisdictions": b["jurisdiction"], "url": t["state_link"],
                        "source_type": "official", "capture": "yes", "retrieved_at": f"{now:%Y-%m-%dT%H:%MZ}",
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "text_file": f"text/{doc_id}.txt",
                        "status": "ok", "provenance": "legiscan_api", "bill": b["bill_key"],
                        "bill_status": f"{b['status']} ({t['type']} {t['date']})", "bill_dates": dates,
                        "effective_clause_verbatim": clause or "not stated in text"}
        print(f"  {doc_id} {b['bill_key']:10} {t['type']:9} {len(body):6} chars · effective: {(clause or 'not stated in text')[:90]}")
    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["doc_id"]))
    print(f"{len(rows)} documents in {MANIFEST.relative_to(ROOT)} · next: make ingest DOC={','.join(sorted(rows))}")


if __name__ == "__main__":
    main()
