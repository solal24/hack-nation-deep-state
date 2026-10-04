"""Step 1 · Law texts -> structured rules (outputs/rules.json).

For each document (starter corpus + corpus_extra/): clean the text -> LLM extracts rules in the
schema format -> each quote is located in the source and replaced by the EXACT source excerpt
(rejected, then retried once, if not found) -> jurisdiction/status/date normalized and schema-checked
-> duplicates merged on (jurisdiction, category, base citation) -> stable ids -> rules.json + audit log.

Run:
  python -m pipeline.extract                     # all documents with text
  python -m pipeline.extract --doc D052,X001     # only these docs (ingest): other docs' rules are kept
  python -m pipeline.extract --verify-only       # re-check quotes of an existing rules.json, no LLM
LLM answers are cached in data/cache/llm/ (same text + prompt + model = same answer, free re-runs).
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import jsonschema
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "starter/corpus"
EXTRA = ROOT / "corpus_extra"
OUT = ROOT / "outputs/rules.json"            # official deliverable (filtered by OFFICIAL_SOURCES)
OUT_ALL = ROOT / "outputs/rules_all.json"    # everything, incl. corpus_extra (for the app)
# Default "starter": corpus_extra rules stay out of the deliverable unless organizers allow them (CLAUDE.md).
OFFICIAL_SOURCES = os.getenv("OFFICIAL_SOURCES", "starter")  # "starter" (RealPage corpus only) or "all"
LOG = ROOT / "outputs/extract_log.jsonl"
CACHE = ROOT / "data/cache/llm"
SCHEMA = json.loads((ROOT / "starter/schema/rule_record.schema.json").read_text(encoding="utf-8"))
AS_OF = "2026-10-01"
CHUNK_CHARS = 45000

CATEGORIES = ["rent_increase_limits", "just_cause_eviction", "security_deposits",
              "application_screening_fees", "screening_restrictions", "algorithmic_rent_setting"]
STATUSES = ["in_force", "not_yet_effective", "pending", "failed"]
STAGE = {"pending": 0, "not_yet_effective": 1, "in_force": 2, "failed": 2}   # legal stage, for duplicate merging
STATES = {"CA": "California", "NJ": "New Jersey", "MA": "Massachusetts"}
CITIES = {"Los Angeles": "CA", "San Francisco": "CA", "San Diego": "CA", "Berkeley": "CA", "Santa Ana": "CA",
          "Jersey City": "NJ", "Hoboken": "NJ", "Newark": "NJ", "Boston": "MA", "Cambridge": "MA"}


# ---------- what the LLM must return ----------

class Coverage(BaseModel):
    built_before: Optional[str] = Field(None, description="Covers buildings built/first occupied BEFORE this date (YYYY-MM-DD), e.g. SF rent control '1979-06-13'")
    built_after: Optional[str] = Field(None, description="Covers buildings built AFTER this date (YYYY-MM-DD)")
    built_cutoff_uses_co_date: bool = Field(False, description="True if the cutoff is a certificate-of-occupancy date rather than year built")
    exempt_if_built_within_years: Optional[int] = Field(None, description="Rolling exemption for newer buildings, e.g. 15 for 'certificate of occupancy within the previous 15 years'")
    min_units: Optional[int] = Field(None, description="Minimum number of units in the building for the rule to apply")
    max_units: Optional[int] = Field(None, description="Maximum number of units for the rule to apply")
    excludes_owner_occupied_min_units: Optional[int] = Field(None, description="Owner-occupied buildings with this many units or fewer are exempt")
    excludes_single_family: bool = False
    notes: Optional[str] = Field(None, description="Other coverage conditions in plain words (owner type, subsidized housing...)")


class ExtractedRule(BaseModel):
    jurisdiction: str = Field(description="'CA', 'NJ', 'MA' for state law, or 'City, ST' e.g. 'San Francisco, CA'")
    category: str = Field(description="One of: " + ", ".join(CATEGORIES))
    status: str = Field(description=f"As of {AS_OF}: " + ", ".join(STATUSES))
    title: str
    requirement: str = Field(description="One or two plain-language sentences a renter can understand")
    key_value: Optional[str] = Field(None, description="Headline number or formula. REQUIRED whenever the law states a number, cap, fee, date or formula")
    sets_limit: bool = Field(False, description="True if this rule itself imposes a substantive limit/protection (cap, ban, required cause); False if it is only an exemption, notice or procedure")
    coverage_conditions: Optional[Coverage] = None
    exemptions: Optional[str] = None
    overrides_citations: List[str] = Field(default_factory=list, description="Citations of rules THIS rule supersedes/replaces (e.g. a local rent ordinance supersedes 'Cal. Civ. Code § 1947.12')")
    preempts_local: bool = Field(False, description="True only if the text explicitly preempts or prohibits conflicting local ordinances")
    conflicting_sources: bool = Field(False, description="True only if the document itself shows two different values/dates for the same rule")
    interaction: Optional[str] = None
    effective_date: Optional[str] = Field(None, description="Date the rule FIRST took effect (YYYY, YYYY-MM or YYYY-MM-DD). Not the date of a later amendment")
    penalty: Optional[str] = None
    citation: str = Field(description="Official cite at section level, e.g. 'Cal. Civ. Code § 1947.12'")
    quoted_span: str = Field(description="EXACT contiguous text copied character for character from the document (20-400 chars) that supports the rule")
    confidence: float = Field(description="0 to 1")
    conflict_note: Optional[str] = Field(None, description="Any ambiguity worth human review")


class Extraction(BaseModel):
    rules: List[ExtractedRule]


PROMPT = """You extract housing rules from one legal source document for a rental-law navigator.
Document {doc_id} · jurisdiction(s): {jurisdictions} · source: {url} · query date: {as_of}

Extract every distinct rule in these 6 categories ONLY:
- rent_increase_limits: rent caps / allowable increases, who is covered, local vs state precedence
- just_cause_eviction: allowed causes, notice, relocation assistance, coverage
- security_deposits: maximum deposit, exceptions, effective date
- application_screening_fees: application/screening fee caps, allowed upfront charges, refunds
- screening_restrictions: limits on criminal-history, source-of-income or other tenant screening
- algorithmic_rent_setting: bans/limits on algorithmic rent-pricing software

Rules:
- ONE record per law (statute section, ordinance or bill) per category. Do NOT create separate records for exceptions, procedures or sub-clauses: put exceptions in `exemptions`, details in `requirement`/`interaction`. Typical documents yield 1-4 records.
- jurisdiction: exactly 'CA', 'NJ', 'MA', or one of 'Los Angeles, CA', 'San Francisco, CA', 'San Diego, CA', 'Berkeley, CA', 'Santa Ana, CA', 'Jersey City, NJ', 'Hoboken, NJ', 'Newark, NJ', 'Boston, MA', 'Cambridge, MA'.
- citation: SECTION level, standard form, no subsection letters/numbers: 'Cal. Civ. Code § 1947.12', 'Mass. Gen. Laws ch. 186, § 15B', 'N.J.S.A. 46:8-21.2', 'S.F. Admin. Code ch. 37', 'MA S.2983'. New Jersey session laws: 'P.L.2026, c.43'. If a summary page names the underlying law, cite the law.
- quoted_span MUST be copied exactly from the document below (same words, same order), 20-400 characters, one contiguous passage. Never paraphrase, never use '...'.
- key_value is REQUIRED whenever the law states a number, cap, fee, percentage or formula (e.g. '1 month's rent', '5% + CPI, max 10%', '$50').
- status as of {as_of}: bills/proposals are 'pending'; bills from an earlier legislative session that did not pass, and struck or defeated ballot questions, are 'failed'; enacted with a later effective date is 'not_yet_effective'; otherwise 'in_force'.
- effective_date = when the rule FIRST took effect, not a later amendment. California statutes without an urgency clause take effect January 1 of the year after they are chaptered (e.g. chaptered Oct 2025 -> 2026-01-01).
- Council motions, staff reports, press releases about proposals and FAQs about procedures are NOT rules unless they state an enacted or pending law.
- coverage_conditions: only facts about the BUILDING (year built / certificate of occupancy, number of units, owner occupancy, single-family). Leave fields null when the text says nothing.
- sets_limit: true only for a substantive limit/protection; false for a pure exemption, notice or procedure record.
- preempts_local / conflicting_sources: only when the text explicitly says so. Other doubts go in conflict_note.
- Do not invent rules or citations. If the document contains no rule in the 6 categories, return an empty list.

DOCUMENT:
{text}"""

RETRY = """

IMPORTANT: in a previous attempt, these quoted_span values were NOT found verbatim in the document.
For each such rule, copy a passage exactly as written in the document (same words, same order, no '...'):
{bad}"""

SYSTEM = "You are a meticulous legal data extractor. Accuracy over coverage. Answer only with the requested JSON."


# ---------- corpus ----------

def load_manifest():
    """Starter manifest + corpus_extra manifest (Elie's supplemental texts). meta['_base'] = folder of text_file."""
    docs = {}
    for base, path in ((CORPUS, CORPUS / "corpus_manifest.csv"), (EXTRA, EXTRA / "manifest.csv")):
        if path.exists():
            for r in csv.DictReader(path.open(encoding="utf-8")):
                r["_base"] = str(base)
                r.setdefault("provenance", "starter" if base == CORPUS else "")
                if base == CORPUS:
                    r["provenance"] = "starter"
                docs[r["doc_id"]] = r
    return docs


def source_text(meta):
    return (Path(meta["_base"]) / meta["text_file"]).read_text(encoding="utf-8")


NAV = re.compile(r"^(skip to .*|home|search|menu|login|sitemap|accessibility|faq|feedback|x|>>|print page|"
                 r"prev(ious)?|next|go|share|close|toggle navigation)$", re.I)


def clean(text):
    """Drop the SOURCE/RETRIEVED header, web-navigation lines and menu runs; keep tables and legal text."""
    body = [l for l in text.splitlines() if not l.startswith(("SOURCE:", "RETRIEVED:"))]
    body = [l for l in body if not NAV.match(l.strip())]
    # menu = run of 5+ consecutive very short lines without numbers ($, %, digits keep table rows)
    short = [0 < len(l.split()) <= 3 and not re.search(r"[\d$%]", l) for l in body]
    kept, i = [], 0
    while i < len(body):
        j = i
        while j < len(body) and short[j]:
            j += 1
        if j - i >= 5:
            i = j
            continue
        kept.append(body[i])
        i += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def chunks(text):
    """Split long docs on paragraphs, falling back to lines when paragraphs are huge."""
    if len(text) <= CHUNK_CHARS:
        return [text]
    units = text.split("\n\n")
    if max(len(u) for u in units) > CHUNK_CHARS:
        units = text.split("\n")
    parts, cur = [], ""
    for u in units:
        if len(cur) + len(u) > CHUNK_CHARS and cur:
            parts.append(cur)
            cur = ""
        cur += u + "\n"
    return parts + [cur] if cur.strip() else parts


# ---------- quotes: locate the exact excerpt in the source ----------

_SQ, _DQ, _DASH = "['‘’]", "[\"“”]", "[-–—]"
QUOTE_CHARS = {"'": _SQ, "‘": _SQ, "’": _SQ, '"': _DQ, "“": _DQ, "”": _DQ,
               "-": _DASH, "–": _DASH, "—": _DASH}


def exact_span(span, source):
    """Find `span` in `source` tolerating whitespace/case/quote/dash differences.
    Returns the EXACT source excerpt, or None if not found."""
    tokens = (span or "").split()
    if len("".join(tokens)) < 15:
        return None
    pattern = r"\s+".join("".join(QUOTE_CHARS.get(c, re.escape(c)) for c in t) for t in tokens)
    m = re.search(pattern, source, re.I)
    return m.group(0) if m else None


# ---------- normalization ----------

def canon_jurisdiction(j):
    """-> ('CA'|'NJ'|'MA'|'City, ST', 'state'|'city') or (None, None)."""
    s = (j or "").strip()
    s = re.sub(r"^(the\s+)?(city and county of|city of|state of)\s+", "", s, flags=re.I)
    if re.search(r"\bcounty\b", s, re.I):  # county-level rules are out of our 13 jurisdictions
        return None, None
    for code, name in STATES.items():
        if s.upper() == code or s.lower() == name.lower():
            return code, "state"
    for candidate in (s, re.sub(r"\s+city(?=,|$)", "", s, flags=re.I)):  # 'Jersey City' must keep its 'City'
        for city, st in CITIES.items():
            if candidate.lower().startswith(city.lower()):
                return f"{city}, {st}", "city"
    return None, None


def canon_date(d):
    """'July 1, 2027' / '2026-7-1' / '2027' -> 'YYYY[-MM[-DD]]' or None."""
    if not d:
        return None
    d = str(d).strip()
    if re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", d):
        return d
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", d)
    if m:
        return f"{m[1]}-{int(m[2]):02d}" + (f"-{int(m[3]):02d}" if m[3] else "")
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%B %Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(d, fmt)
            return dt.strftime("%Y-%m" if fmt == "%B %Y" else "%Y-%m-%d")
        except ValueError:
            pass
    return None


CITE_ALIASES = [
    (r"\b(massachusetts general laws|mass\.?\s*gen\.?\s*laws|m\.?\s*g\.?\s*l\.?|g\.?\s*l\.?)\b", "mgl"),
    (r"\b(california civil code|cal\.?\s*civ\.?\s*code|civil code)\b", "calciv"),
    (r"\b(california government code|cal\.?\s*gov\.?\s*code|government code)\b", "calgov"),
    (r"\bn\.?\s*j\.?\s*s\.?\s*a\.?\b", "njsa"),
    (r"\b(chapter|ch\.|c\.)\s*", "c"),
    (r"\b(section|sec\.|sections)\s*", ""),
]


def cite_key(c):
    """Base-section key: strips subsections '(1)(b)', 'et seq', aliases. Keeps ':' '-' '.' to avoid false merges."""
    s = (c or "").lower()
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"\bet\s+seq\.?", "", s)
    for pat, rep in CITE_ALIASES:
        s = re.sub(pat, rep, s)
    s = re.sub(r"[^a-z0-9.:\-]", "", s)
    return re.sub(r"(?<!\d)\.|\.(?!\d)", "", s).strip("-")  # keep decimal points (1947.12), drop the rest


def stable_id(jurisdiction, category, citation):
    return "r-" + hashlib.sha1(f"{jurisdiction}|{category}|{cite_key(citation)}".encode()).hexdigest()[:8]


# ---------- LLM ----------

# Backend: "claude_cli" (default) = Claude Code headless (`claude -p`) logged into the account in
# CLAUDE_CLI_CONFIG_DIR (Solal: Enterprise login in ~/.claude-enterprise, no API credits used).
# "api" = Anthropic API key from .env (pipeline/llm.py).
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")  # LLM_BACKEND / ANTHROPIC_API_KEY live in .env (never committed)
BACKEND = os.getenv("LLM_BACKEND", "claude_cli")
API_MODEL = os.getenv("EXTRACT_API_MODEL", "claude-sonnet-5")  # same model family as the CLI default
CLI_CONFIG_DIR = os.path.expanduser(os.getenv("CLAUDE_CLI_CONFIG_DIR", "~/.claude-enterprise"))
CLI_MODEL = os.getenv("CLAUDE_CLI_MODEL", "sonnet")


def claude_binary():
    found = shutil.which("claude")
    if found:
        return found
    bundled = sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude")))
    if not bundled:
        raise SystemExit("Claude Code binary not found. Install Claude Code or set LLM_BACKEND=api.")
    return bundled[-1]


def call_claude_cli(prompt):
    """One headless Claude Code call with a JSON schema, in an empty folder, using the Enterprise login."""
    if not os.path.isdir(CLI_CONFIG_DIR):
        raise SystemExit(f"No Claude login in {CLI_CONFIG_DIR}. Run once in a terminal:\n"
                         f"  CLAUDE_CONFIG_DIR={CLI_CONFIG_DIR} \"{claude_binary()}\"\n"
                         "then /login with the Enterprise account, then /exit.")
    env = {**os.environ, "CLAUDE_CONFIG_DIR": CLI_CONFIG_DIR}
    env.pop("ANTHROPIC_API_KEY", None)  # use the logged-in account, never an API key
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [claude_binary(), "-p", "--output-format", "json", "--model", CLI_MODEL,
             "--json-schema", json.dumps(Extraction.model_json_schema()),
             "--system-prompt", SYSTEM, "--setting-sources", ""],
            input=prompt, capture_output=True, text=True, env=env, cwd=tmp, timeout=900)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed ({proc.returncode}): {(proc.stderr or proc.stdout)[:500]}")
    out = json.loads(proc.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude -p error: {str(out.get('result'))[:500]}")
    data = out.get("structured_output")
    if data is None:
        text = out.get("result", "")
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
    return Extraction.model_validate(data)


def call_llm(prompt):
    """Cached structured extraction. Key = prompt + system + model + schema; atomic writes."""
    CACHE.mkdir(parents=True, exist_ok=True)
    # Cache key ignores the backend (CLI login or API key = same Sonnet model), so switching backend
    # reuses the 54 cached answers. Kept identical to the original key format for compatibility.
    fingerprint = json.dumps([prompt, SYSTEM, "claude_cli", CLI_MODEL, Extraction.model_json_schema()], sort_keys=True)
    path = CACHE / f"{hashlib.sha256(fingerprint.encode()).hexdigest()[:20]}.json"
    if path.exists():
        return Extraction.model_validate_json(path.read_text(encoding="utf-8"))
    if BACKEND == "api":
        from pipeline.llm import ask_json
        result = ask_json(prompt, Extraction, system=SYSTEM, model=API_MODEL)
    else:
        result = call_claude_cli(prompt)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return result


# ---------- one document ----------

def to_record(rule, doc_id, meta, span):
    jur, level = canon_jurisdiction(rule.jurisdiction)
    cov = rule.coverage_conditions.model_dump(exclude_none=True) if rule.coverage_conditions else None
    cov = {k: v for k, v in (cov or {}).items() if v not in (False, None, "")} or None
    return {
        "team_rule_id": stable_id(jur, rule.category, rule.citation), "jurisdiction": jur, "level": level,
        "category": rule.category, "status": rule.status, "title": rule.title,
        "requirement": rule.requirement, "key_value": rule.key_value,
        "coverage_conditions": cov, "exemptions": rule.exemptions,
        "overrides": [], "overrides_citations": rule.overrides_citations,
        "interaction": rule.interaction, "effective_date": canon_date(rule.effective_date),
        "citation": rule.citation, "source_doc_id": doc_id, "source_url": meta["url"],
        "retrieved_at": meta.get("retrieved_at"), "provenance": meta.get("provenance") or "starter",
        "review_status": None if (meta.get("provenance") or "starter") == "starter" else "to_review",
        "quoted_span": span, "confidence": max(0.0, min(1.0, float(rule.confidence))),
        "sets_limit": rule.sets_limit, "preempts_local": rule.preempts_local,
        "conflict_flag": bool(rule.preempts_local or rule.conflicting_sources),
        "conflict_note": rule.conflict_note, "penalty": rule.penalty,
    }


def check(rule, raw):
    """-> (record-ready span, reason) ; reason is None when the rule is accepted."""
    if rule.category not in CATEGORIES:
        return None, f"bad category {rule.category}"
    if rule.status not in STATUSES:
        return None, f"bad status {rule.status}"
    if canon_jurisdiction(rule.jurisdiction)[0] is None:
        return None, f"unknown jurisdiction {rule.jurisdiction}"
    if rule.effective_date and not canon_date(rule.effective_date):
        return None, f"bad effective_date {rule.effective_date}"
    span = exact_span(rule.quoted_span, raw)
    if span is None:
        return None, "quote not found in source"
    return span, None


def extract_doc(doc_id, meta, log):
    raw = source_text(meta)
    kept = []
    for i, part in enumerate(chunks(clean(raw))):
        prompt = PROMPT.format(doc_id=doc_id, jurisdictions=meta["jurisdictions"], url=meta["url"], as_of=AS_OF, text=part)
        attempt, bad = call_llm(prompt).rules, []
        for retry in (False, True):
            for rule in attempt:
                span, reason = check(rule, raw)
                log.append({"doc_id": doc_id, "chunk": i, "retry": retry, "citation": rule.citation,
                            "category": rule.category, "accepted": reason is None, "reason": reason,
                            "span": rule.quoted_span[:120]})
                if reason is None:
                    rec = to_record(rule, doc_id, meta, span)
                    try:
                        jsonschema.validate(rec, SCHEMA)
                        kept.append(rec)
                    except jsonschema.ValidationError as e:
                        log[-1].update(accepted=False, reason=f"schema: {e.message[:100]}")
                elif not retry and reason == "quote not found in source":
                    bad.append(f"- {rule.citation} ({rule.category}): {rule.quoted_span[:200]!r}")
            if retry or not bad:
                break
            accepted = {(r["category"], cite_key(r["citation"])) for r in kept}
            attempt = [r for r in call_llm(prompt + RETRY.format(bad="\n".join(bad))).rules
                       if (r.category, cite_key(r.citation)) not in accepted]
    return kept


# ---------- assemble ----------

def assemble(records):
    """Merge duplicates on (jurisdiction, category, base citation); keep highest confidence;
    then resolve overrides_citations -> team_rule_ids."""
    best = {}
    for r in records:
        k = r["team_rule_id"]
        if k not in best:
            best[k] = r
            continue
        # A supplied-corpus rule always wins over a corpus_extra duplicate (so rules.json never loses it),
        # then the highest confidence.
        # Exception: an official corpus_extra text showing the same law at a later legal stage (a supplied staff
        # report says "pending", the city's code shows it enacted) wins, keeping its outside-corpus warning.
        rank = lambda x: (x.get("provenance", "starter") == "starter", x["confidence"])
        keep, other = (r, best[k]) if rank(r) > rank(best[k]) else (best[k], r)
        if keep.get("provenance", "starter") == "starter" != other.get("provenance", "starter") \
                and STAGE.get(other["status"], 0) > STAGE.get(keep["status"], 0):
            keep, other = other, keep
        also = set(keep.get("also_in") or []) | set(other.get("also_in") or []) | {other["source_doc_id"]}
        keep["also_in"] = sorted(also - {keep["source_doc_id"]})
        keep["overrides_citations"] = sorted(set(keep.get("overrides_citations") or []) | set(other.get("overrides_citations") or []))
        best[k] = keep
    rules = sorted(best.values(), key=lambda r: (r["jurisdiction"], r["category"], r["citation"]))
    for r in rules:
        wanted = {cite_key(c) for c in r.get("overrides_citations") or []}
        r["overrides"] = [o["team_rule_id"] for o in rules
                          if o is not r and o["category"] == r["category"] and cite_key(o["citation"]) in wanted]
    return rules


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", help="only these doc_ids, comma-separated (e.g. D052 or D024,X001)")
    ap.add_argument("--workers", type=int, default=4, help="documents processed in parallel")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="write rules.json even if some documents failed")
    args = ap.parse_args()
    manifest = load_manifest()

    if args.verify_only:
        rules = json.loads(OUT.read_text(encoding="utf-8"))["rules"]
        bad = [r["team_rule_id"] for r in rules if r["quoted_span"] not in source_text(manifest[r["source_doc_id"]])]
        print(f"{len(rules)} rules · quotes found verbatim (exact, case-sensitive): {len(rules) - len(bad)} · failed: {bad}")
        return

    wanted = set(args.doc.split(",")) if args.doc else None
    # status "reference_only" (corpus_extra): kept for people to read, never extracted (e.g. IP 25-21's petition
    # text alone would yield a "pending" rent cap; the SJC docket X007 records it as failed).
    extractable = {d for d, m in manifest.items() if m.get("text_file") and m.get("status") != "reference_only"}
    docs = {d: m for d, m in manifest.items() if d in extractable and (not wanted or d in wanted)}
    log, records, failed = [], [], []

    def run(item):
        doc_id, meta = item
        doc_log = []
        try:
            recs = extract_doc(doc_id, meta, doc_log)
        except Exception as e:  # one failing document must not kill the run
            print(f"{doc_id} · FAILED: {str(e)[:200]}", flush=True)
            return doc_id, None, doc_log
        print(f"{doc_id} · {meta['jurisdictions']:<20} · {len(recs)} rules kept", flush=True)
        return doc_id, recs, doc_log

    with ThreadPoolExecutor(args.workers) as pool:
        for doc_id, recs, doc_log in pool.map(run, docs.items()):
            log += doc_log
            if recs is None:
                failed.append(doc_id)
            else:
                records += recs

    # keep previous rules of documents not re-extracted (ingest) or that failed this run
    previous = OUT_ALL if OUT_ALL.exists() else OUT
    if previous.exists():
        redone = {d for d in docs if d not in failed}
        # drop previous rules whose document was re-extracted, removed, or set to reference_only
        records = [r for r in json.loads(previous.read_text(encoding="utf-8"))["rules"]
                   if r["source_doc_id"] not in redone and r["source_doc_id"] in extractable] + records
    if failed and not args.force:
        print(f"\n{len(failed)} document(s) failed: {failed}. rules.json NOT written (re-run, or --force).")
        return
    rules = assemble(records)
    from pipeline.coverage_link import link   # rate pages without building coverage get the city program's
    print(f"coverage linking: {link(rules, log=lambda m: None)} rules")
    OUT_ALL.write_text(json.dumps({"rules": rules}, indent=2, ensure_ascii=False), encoding="utf-8")
    official = rules if OFFICIAL_SOURCES == "all" else [r for r in rules if r.get("provenance", "starter") == "starter"]
    OUT.write_text(json.dumps({"rules": official}, indent=2, ensure_ascii=False), encoding="utf-8")
    extra = sum(r.get("provenance", "starter") != "starter" for r in rules)
    print(f"rules_all.json: {len(rules)} rules ({extra} from corpus_extra) · rules.json (official, sources={OFFICIAL_SOURCES}): {len(official)}")
    with LOG.open("a", encoding="utf-8") as f:
        run_id = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        for entry in log:
            f.write(json.dumps({"run": run_id, "model": CLI_MODEL if BACKEND == "claude_cli" else API_MODEL, **entry}) + "\n")
    accepted = sum(e["accepted"] for e in log)
    print(f"\n{len(rules)} rules -> {OUT.relative_to(ROOT)} · extracted {len(log)} · accepted {accepted} · rejected {len(log) - accepted}"
          + (f" · failed docs {failed}" if failed else ""))


if __name__ == "__main__":
    main()
