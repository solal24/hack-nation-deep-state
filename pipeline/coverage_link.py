"""Coverage linking · which buildings a local rent-control program covers, across documents.

Problem: a city's rent-increase rule often comes from a rates page ("1.6% for 3/1/2026-2/28/2027", "3% for
2025-26") that never says which buildings are covered; the coverage test (SF: certificate of occupancy on or
before 1979-06-13; LA: built on or before 1978-10-01) sits in another document of the same city. With no
building condition the engine would apply the cap to every building, new construction included: a guess.

For each city rent_increase_limits rule that sets a limit but has no building condition:
  1. sibling: another rule of the same city and category has building conditions (the program's coverage
     rule, e.g. LA RSO overview) -> use them. Deterministic, no LLM.
  2. corpus: otherwise the LLM reads that city's supplied documents and returns the program's coverage only
     with a sentence quoted verbatim from the document (checked in code, like every rule quote), and only
     if that sentence contains the cutoff it reports. Cached in data/cache/llm/.
  3. neither: left unchanged, and said so.
Each linked rule records where its coverage came from in `coverage_source` (doc, quote or sibling rule).
Rules are never written by hand: this only fills `coverage_conditions` from extracted or quoted evidence.

Run: python -m pipeline.coverage_link        (updates outputs/rules.json and rules_all.json in place)
     also called by pipeline.extract after every extraction.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data/cache/llm"
OUTPUTS = [ROOT / "outputs/rules_all.json", ROOT / "outputs/rules.json"]
BUILDING = ("built_before", "built_after", "exempt_if_built_within_years", "min_units", "max_units",
            "excludes_owner_occupied_min_units", "excludes_single_family")
MODEL = os.getenv("EXTRACT_API_MODEL", "claude-sonnet-5")


def building_conditions(rule):
    c = rule.get("coverage_conditions")
    if not isinstance(c, dict):
        return {}
    return {k: c[k] for k in BUILDING + ("built_cutoff_uses_co_date",) if c.get(k)}


def needs_link(rule):
    return (rule.get("level") == "city" and rule["category"] == "rent_increase_limits"
            and rule.get("sets_limit") and rule["status"] in ("in_force", "not_yet_effective")
            and not any(k in building_conditions(rule) for k in BUILDING))


class ProgramCoverage(BaseModel):
    states_coverage: bool = Field(description="True only if the document itself says which buildings the city's "
                                              "rent control / rent stabilization (allowable rent increase limits) "
                                              "covers or exempts based on building facts")
    built_before: Optional[str] = Field(None, description="Covered if built / first certificate of occupancy ON OR BEFORE this date (YYYY-MM-DD)")
    built_after: Optional[str] = Field(None, description="Covered if built AFTER this date (YYYY-MM-DD)")
    built_cutoff_uses_co_date: bool = Field(False, description="True if the cutoff is a certificate-of-occupancy date")
    min_units: Optional[int] = None
    excludes_single_family: bool = False
    quoted_span: Optional[str] = Field(None, description="The sentence stating this coverage, copied EXACTLY from the document (20-400 chars)")


PROMPT = """Document {doc_id} ({url}) is about housing law in {city}.
Question: does this document state which buildings are covered by, or exempt from, {city}'s local rent control /
rent stabilization (the limits on allowable annual rent increases), based on BUILDING facts (year built or
certificate-of-occupancy date, number of units, single-family)?
If yes, fill the fields and copy the exact sentence that states it into quoted_span (same words, same order).
A statement that newer buildings (e.g. certificate of occupancy after a date) are EXEMPT from rent increase limits
means covered buildings are those on or before that date: put that date in built_before.
If the document does not say it, answer states_coverage=false and leave the rest empty. Do not use outside knowledge.

DOCUMENT:
{text}"""


def ask(prompt):
    """Cached structured answer (same prompt + model = same answer, $0 re-runs)."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps(["coverage_link", prompt, MODEL], sort_keys=True).encode()).hexdigest()[:20]
    path = CACHE / f"coverage_{key}.json"
    if path.exists():
        return ProgramCoverage.model_validate_json(path.read_text(encoding="utf-8"))
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    from pipeline.llm import ask_json
    result = ask_json(prompt, ProgramCoverage, system="You are a meticulous legal data extractor. Answer only "
                      "from the document. Accuracy over coverage.", model=MODEL)
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return result


def from_corpus(city):
    """First supplied document of the city whose quoted sentence states the program's building coverage."""
    from pipeline.extract import exact_span, load_manifest, source_text
    for doc_id, meta in sorted(load_manifest().items()):
        if meta["provenance"] != "starter" or meta["jurisdictions"] != city or not meta.get("text_file"):
            continue
        text = source_text(meta)
        ans = ask(PROMPT.format(doc_id=doc_id, url=meta["url"], city=city, text=text[:45000]))
        if not ans or not ans.states_coverage or not ans.quoted_span:
            continue
        span = exact_span(ans.quoted_span, text)
        cond = {k: v for k, v in ans.model_dump().items() if v and k in BUILDING + ("built_cutoff_uses_co_date",)}
        # the quote must contain what it is used for: the cutoff year / unit count, not just any sentence
        evidence = [v[:4] for k, v in cond.items() if k in ("built_before", "built_after")] + \
                   [str(v) for k, v in cond.items() if k == "min_units"]
        if span and any(k in BUILDING for k in cond) and all(e in span for e in evidence):
            return cond, {"method": "corpus", "doc_id": doc_id, "source_url": meta["url"], "quoted_span": span}
    return None, None


def link(rules, log=print):
    linked, corpus_cache = 0, {}
    # program coverage comes only from conditions extraction itself produced, never from a rule linked here
    own = [o for o in rules if not o.get("coverage_source") and any(k in building_conditions(o) for k in BUILDING)]
    for r in rules:
        if not needs_link(r):
            continue
        siblings = {json.dumps(building_conditions(o), sort_keys=True): o for o in own
                    if o is not r and o["jurisdiction"] == r["jurisdiction"] and o["category"] == r["category"]}
        if len(siblings) == 1:   # one unambiguous program coverage in this city
            o = next(iter(siblings.values()))
            cond, src = building_conditions(o), {"method": "sibling", "rule_id": o["team_rule_id"],
                                                 "citation": o["citation"], "doc_id": o["source_doc_id"]}
        else:
            if r["jurisdiction"] not in corpus_cache:
                corpus_cache[r["jurisdiction"]] = from_corpus(r["jurisdiction"])
            cond, src = corpus_cache[r["jurisdiction"]]
        if not cond:
            log(f"  {r['team_rule_id']} {r['jurisdiction']:16} {r['citation'][:34]:34} no building coverage found: unchanged")
            continue
        base = r.get("coverage_conditions") if isinstance(r.get("coverage_conditions"), dict) else \
            ({"notes": r["coverage_conditions"]} if r.get("coverage_conditions") else {})
        r["coverage_conditions"] = {**base, **cond}
        r["coverage_source"] = src
        linked += 1
        log(f"  {r['team_rule_id']} {r['jurisdiction']:16} {r['citation'][:34]:34} <- {src['method']} "
            f"{src.get('rule_id') or src['doc_id']}: {cond}")
    return linked


def main():
    for path in OUTPUTS:
        data = json.loads(path.read_text(encoding="utf-8"))
        print(f"{path.relative_to(ROOT)}:")
        n = link(data["rules"])
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  {n} rules linked")


if __name__ == "__main__":
    main()
