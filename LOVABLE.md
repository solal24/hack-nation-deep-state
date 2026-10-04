# Lovable prompt pack · Covenant (Rental Housing Law Navigator)

How to use it (one person drives Lovable, the others keep working on the pipeline):
1. Paste **Block K** into Lovable → Project settings → Knowledge (persists across every message).
2. Upload `outputs/app/navigator_data.json` to `public/data/navigator_data.json` (replace the old one). Regenerate it with `python -m pipeline.app_bundle` whenever rules change, and re-upload.
3. Send **Rounds 1 to 6 one at a time**. After each round, open the preview and check its "Done when" list. If something fails, send a short fix message, never the next round on top of a broken one.
4. Round 1 in Plan mode (Lovable shows its plan, you approve). Later rounds in normal mode.
5. Feature freeze at 05:00. Rounds 7+ are optional.

Why this structure: Lovable stops halfway on huge prompts (our first run did). Knowledge holds what never changes (truth rules, design system, data contract), each round holds one goal with exact acceptance checks. The legal logic is given as code (Round 1), so the AI builder never invents a rule.

---

## Block K · Project Knowledge (paste as-is)

```
PRODUCT
Covenant: rental housing law, address by address. For any of 500 sample buildings in CA, NJ and MA (10 cities), on any date, it shows which laws apply in 6 categories (rent increases, eviction protections, security deposits, application fees, tenant screening, algorithmic rent setting), with the exact quoted source text, and says "unknown" instead of guessing. Built by Team Deep State (Hack-Nation 2026, RealPage challenge). Audience: renters, landlords and property managers, legislators and their staff, public housing offices. Judges value: every answer traceable, enacted / pending / not-yet-effective kept apart, honest unknowns, conflicts flagged.

TRUTH RULES (never break)
1. The app never decides law by itself. Verdicts come from public/data/navigator_data.json ("results") or from src/lib/engine.ts (an exact port of our Python engine). Never add, edit or summarise a rule in code. Never call an AI model to produce a verdict.
2. Every verdict shows: the result, the citation, the as-of date. One click shows the verbatim quoted_span, source_url, retrieved_at, and which building facts were used and where each came from.
3. Five results only, never merged: applies, unknown, superseded, not_yet_effective, pending. Rules that do not apply are not shown (say so once: "Rules that don't cover this building are hidden").
4. "unknown" always names the missing fact and what would settle it. Never show unknown as a red error or as "does not apply".
5. Anything not from the supplied data carries its warning text right next to it: watchlist bills and council items (field "warning"), facts typed by the user ("Based on what you entered, not verified"), rules with review_status "to_review" ("From an official source outside the challenge pack, pending review").
6. The disclaimer is visible on every screen (footer + report header): "Not legal advice. Prototype summary of public law for the Hack-Nation challenge; verify with the cited source."
7. Legal text (requirement, quoted_span, exemptions, titles) stays in English in every language, with the line "Legal text is shown in the original English."
8. Laws follow the legal city (Census incorporated place), never the ZIP or the postal city. When postal_city differs from legal_city, show both: "Mailing city: South Boston · Legal city: Boston".

DATA CONTRACT (public/data/navigator_data.json, ~1.7 MB, load once, index in memory)
disclaimer, generated_at, default_as_of "2026-10-01", as_of_dates ["2025-12-31","2026-01-02","2026-10-01","2027-07-02"], categories[6], jurisdictions[13]
rules[]: team_rule_id, jurisdiction ("CA" | "Los Angeles, CA"...), level (state|city), category, status (in_force|pending|not_yet_effective|failed), title, requirement, key_value, coverage_conditions {built_before, built_after, built_cutoff_uses_co_date, exempt_if_built_within_years, min_units, max_units, excludes_single_family, excludes_owner_occupied_min_units, notes}, exemptions, effective_date, citation, source_doc_id, source_url, retrieved_at, quoted_span, confidence, conflict_note, provenance, review_status, sets_limit, preempts_local, overrides, conflict_flag, penalty
addresses[]: id, street, postal_city, state, zip, zip_supplied, legal_city, legal_city_source (census_batch|census_oneline|postal_fallback), county, year_built, units_min, units_max (null = unbounded), units_source (supplied|use_code|unknown), use_description, source_dataset, retrieved_at, lat, lon
results[as_of][address_id] = [rule_id, result, missing_facts[], conflict_flag, superseded_by?, conflict_with[]?]
coverage[jurisdiction][category] = [{id, status}]  (empty = no rule in our sources)
unknowns[] = {city, missing_fact, answers}
changes{T1..T5} = {title, type, expected_behavior, as_of_before, as_of_after, rule_mapping, notes, affected, conflicts, affected_address_ids[], conflict_flag_address_ids[]}
radar = {items{jurisdiction: [{id, kind, verified, rule_id, title, citation, categories[], status, certainty, last_action, last_action_date, days_since_last_action, in_scope, change_tests[], effective_date, link, warning}]}, closed{jurisdiction: [...]}, council_monitoring{city: text}, legend{certainty: text}}
  certainty, most to least certain: scheduled > enacted = adopted > verified_pending = moving > stalled > signal
stats = {rules, rules_by_status, quotes_verified, source_docs_used, starter_docs, starter_docs_with_text, extra_official_docs, addresses, geocoded, postal_city_corrected, year_built_known, units_supplied, units_from_use_code, results_default_date, answers_default_date}
demo[] = {id, why}

FACT LABELS AND WHERE TO FIND THEM (use these exact words)
year_built: "Year built" · where: "County assessor / property tax record"
certificate_of_occupancy_date: "Certificate of occupancy date" · why: "The building was finished in the cutoff year, so the year alone can't settle it" · where: "City building department records"
exact_construction_date: "Exact construction date" · same why · where: "City building department or assessor records"
units: "Number of units" · where: "Assessor record, or count the units / ask the landlord"
owner_occupancy: "Does the owner live in the building?" · where: "Ask the landlord; homestead exemption records"

DESIGN SYSTEM (looks like a serious legal research tool, not an AI-generated SaaS page)
References in spirit: GOV.UK Design System (plain language, status tags, clarity), Stripe Docs (calm hierarchy), Bloomberg Law / Westlaw (dense, serif headings, citations everywhere), Linear (crisp hairlines). Not a startup landing page.
Fonts (Google Fonts): headings "Newsreader" (serif, weights 500/600, tight leading 1.15, letter-spacing -0.01em); UI and body "IBM Plex Sans" (400/500/600, 15px base, line-height 1.55); citations, IDs, dates, numbers "IBM Plex Mono" (400/500, tabular figures). Never Inter.
Colors (CSS variables, light theme first; add dark later):
  --paper #F6F5F1 (page) · --surface #FFFFFF (panels) · --ink #15171C (text) · --ink-2 #4B5059 (secondary) · --ink-3 #7A7F87 (meta) · --line #E2E0D9 (hairlines) · --brand #6B1E2B (oxblood: wordmark, links, focus ring, primary button) · --brand-tint #F3E9EA
  Status (always icon + word + color, never color alone):
  applies #0F6B4C on #E7F2EC, icon CircleCheck
  unknown #8A5300 on #FBF1DE, icon CircleHelp, plus a subtle diagonal hatch on the row background
  superseded #5E636B on #EEEEEC, icon ArrowDownRight, citation struck through, "Governed by: <citation>"
  not_yet_effective #1F4C8F on #E7EEF8, icon CalendarClock, "From <date>"
  pending #5E636B on transparent with a 1px dashed border, icon FileClock, "Bill, not law"
  conflict marker #A3261B, icon TriangleAlert, "Possible conflict, flagged for review"
Shape: radius 4px (6px max), 1px hairline borders, no drop shadows except menus/drawers, no gradients, no glassmorphism, no blur, no glow.
Layout: left-aligned text, max content width 1200px, 8px spacing grid, generous but uneven rhythm (mix full-width tables, two-column splits, lists). Avoid rows of three identical cards. Tables are first-class (sticky headers, mono numbers, right-aligned figures).
Icons: lucide-react only, 16px, stroke 1.75. No emoji anywhere. No stock photos, no illustrations, no AI art. The only imagery is data: a small static map tile per address is optional, never decorative.
Motion: 120-180ms ease-out on hover/open only. No scroll-triggered animations, no typewriter, no counters that spin.
Accessibility: WCAG AA contrast, visible focus ring (2px --brand), full keyboard use, 44px touch targets on mobile, aria-labels on icon buttons.

COPY RULES
Sentence case. Concrete verbs (check, compare, cite, export). No "AI-powered", "unlock", "seamless", "empower", "revolutionize", "magic", "smart". No exclamation marks. Numbers in mono. Every empty state says what is missing and what to do. Buttons say exactly what they do ("Show source", "Export CSV", "Check with this year").

ROLES (a lens on the same verdicts, never different law)
renter: "Renter" · landlord: "Landlord / property manager" · legislator: "Legislator / staff" · public: "Public office"
The role changes ordering, wording of headings, and which panels are open by default. It is kept in the URL (?role=) and localStorage.

TECH
TanStack Start + React + Tailwind + shadcn/ui (restyled to the tokens above). No backend, no auth, no database. No runtime AI unless a round explicitly asks for it. Keep src/lib/engine.ts identical to the version given in Round 1 unless asked.
```

---

## Round 1 · Foundation (send in Plan mode)

```
Round 1 of 6: foundation. Read the Project Knowledge first; it is the source of truth.

We are rebuilding the UI from scratch with a new design system. The current screens (src/routes/index.tsx, src/components/navigator/*) are replaced. Keep the shadcn primitives in src/components/ui but restyle them to the tokens. Keep public/data/navigator_data.json untouched (it was just replaced with a new version: new fields superseded_by/conflict_with in results, radar, stats, demo, changes with titles).

1. Design system
- Load Newsreader, IBM Plex Sans, IBM Plex Mono from Google Fonts. Put every color in src/styles.css as CSS variables (the Knowledge palette), map them in Tailwind (bg-paper, text-ink, border-line, text-brand...). Restyle Button (primary = solid --brand, secondary = 1px --line border on surface, ghost), Badge, Tabs, Table, Sheet, Tooltip, Input to 4px radius, hairline borders, no shadows.
- Create src/components/StatusTag.tsx: one component for the 5 results + conflict, exactly as specified (icon + word + colors). Used everywhere; no other status styling in the app.

2. Data layer: src/lib/data.ts
- Types for the whole contract (Knowledge > DATA CONTRACT). Load the JSON once (module-level promise), build indexes: rulesById, addressesById, rulesByJurisdiction, search index over street, postal_city, legal_city, zip, id.
- Helper resultRows(addressId, asOf) that turns the tuples into objects {rule, result, missing_facts, conflict_flag, superseded_by, conflict_with}.

3. Engine: create src/lib/engine.ts with EXACTLY this code (a port of our Python engine; do not "improve" it):

<paste ENGINE.TS from the section below>

4. Parity check (this proves the browser engine equals our pipeline)
- Add a vitest test src/test/engine-parity.test.ts: for each of the 4 as_of_dates and each of the 500 addresses, lookup(address, rules, asOf, factsOf(address)) must equal the precomputed results (same rule ids in any order, same result, same missing_facts, same conflict_flag, same superseded_by (null = absent), same set of conflict_with). Read the JSON from public/data with fs.
- Add a hidden route /qa that runs the same comparison in the browser and prints "Engine parity: 0 mismatches over N answers" (or lists the first 20 mismatches). Not linked in the nav.

5. App shell
- Top bar (56px, surface, bottom hairline): wordmark "Covenant" in Newsreader 600 with a small mono suffix "· rental law, address by address"; nav: Lookup, Portfolio, Coverage, Changes, Legislation radar, Method; right side: role switcher (segmented control, 4 roles), language menu (EN / ES / FR, wired in Round 6, show it now).
- Footer on every page: the disclaimer, "Data as of <generated_at> · <stats.rules> rules · <stats.quotes_verified>/<stats.rules> quotes verified word for word", "Team Deep State · Hack-Nation 2026".
- Create empty routes with a proper heading and one line of description each: /portfolio, /coverage, /changes, /radar, /method. Home and /address/$id come in Round 2.
- Mobile: nav collapses into a Sheet menu; role switcher becomes a Select.

Do not build the home page or address report yet. No placeholder lorem ipsum, no fake data.

Done when: fonts and colors visible on every page; StatusTag renders all 6 states on /qa; /qa says 0 mismatches; vitest parity test passes; no TypeScript errors.
```

### ENGINE.TS (paste inside Round 1 where marked)

```ts
// src/lib/engine.ts · exact port of pipeline/engine.py (Team Deep State). Deterministic: no AI, no network.
// Keep in sync with Python. Parity is checked by src/test/engine-parity.test.ts and /qa.
import type { Rule } from "./data";

export type Result = "applies" | "unknown" | "superseded" | "not_yet_effective" | "pending";
export type Reason = { label: string; verdict: boolean | null; fact: string | null };
export type Facts = {
  year_built: number | null;
  units_min: number | null;
  units_max: number | null;
  owner_occupied: boolean | null; // never in the supplied data: only from the user
  built_before: Record<string, boolean>; // user answers: "built / certificate issued before <cutoff ISO date>?"
};
export type Row = {
  rule_id: string;
  result: Result;
  missing_facts: string[];
  reasons: Reason[];
  conflict_flag: boolean;
  conflict_with: string[];
  superseded_by: string | null;
};

export function factsOf(a: { year_built: number | null; units_min: number | null; units_max: number | null }): Facts {
  return { year_built: a.year_built, units_min: a.units_min, units_max: a.units_max, owner_occupied: null, built_before: {} };
}

// Built before/after a cutoff date when we only know the YEAR built. The cutoff year itself is ambiguous
// (unless the cutoff is Jan 1) -> unknown, settled by the certificate of occupancy / exact construction date.
function yearTest(f: Facts, cutoffIso: string, usesCo: boolean, before: boolean): [boolean | null, string | null] {
  if (f.year_built == null) return [null, "year_built"];
  const cy = Number(cutoffIso.slice(0, 4));
  const rest = cutoffIso.slice(4, 10);
  const jan1 = rest === "" || rest === "-01" || rest === "-01-01";
  if (!jan1 && f.year_built === cy) {
    const ans = f.built_before[cutoffIso];
    if (ans === undefined) return [null, usesCo ? "certificate_of_occupancy_date" : "exact_construction_date"];
    return [before ? ans : !ans, null];
  }
  if (before) return [f.year_built < cy, null];
  return [jan1 ? f.year_built >= cy : f.year_built > cy, null];
}

export function cutoffFor(cond: NonNullable<Rule["coverage_conditions"]>, asOf: string): string | null {
  if (typeof cond !== "object") return null;
  if (cond.built_before) return cond.built_before;
  if (cond.built_after) return cond.built_after;
  if (cond.exempt_if_built_within_years) return `${Number(asOf.slice(0, 4)) - cond.exempt_if_built_within_years}${asOf.slice(4)}`;
  return null;
}

export function evaluateCoverage(cond: Rule["coverage_conditions"], f: Facts, asOf: string) {
  const reasons: Reason[] = [];
  if (!cond || typeof cond !== "object") return { verdict: true as boolean | null, missing: [] as string[], reasons };
  const add = (verdict: boolean | null, fact: string | null, label: string) =>
    reasons.push({ verdict, fact: verdict === null ? fact : null, label });
  const usesCo = !!cond.built_cutoff_uses_co_date;
  if (cond.built_before) { const [v, m] = yearTest(f, cond.built_before, usesCo, true); add(v, m, `built before ${cond.built_before}`); }
  if (cond.built_after) { const [v, m] = yearTest(f, cond.built_after, usesCo, false); add(v, m, `built after ${cond.built_after}`); }
  if (cond.exempt_if_built_within_years) {
    const n = cond.exempt_if_built_within_years;
    const [v, m] = yearTest(f, `${Number(asOf.slice(0, 4)) - n}${asOf.slice(4)}`, usesCo, true);
    add(v, m, `older than ${n} years`);
  }
  const lo = f.units_min, hi = f.units_max;
  if (cond.min_units) { const n = cond.min_units; add(lo != null && lo >= n ? true : hi != null && hi < n ? false : null, "units", `at least ${n} units`); }
  if (cond.max_units) { const n = cond.max_units; add(hi != null && hi <= n ? true : lo != null && lo > n ? false : null, "units", `at most ${n} units`); }
  if (cond.excludes_single_family) add(lo != null && lo >= 2 ? true : hi != null && hi < 2 ? false : null, "units", "not a single-family home");
  if (cond.excludes_owner_occupied_min_units) {
    const n = cond.excludes_owner_occupied_min_units; // owner-occupied buildings with <= n units are exempt
    let v: boolean | null = lo != null && lo > n ? true : null;
    if (v === null && f.owner_occupied === false) v = true;
    if (v === null && f.owner_occupied === true && hi != null && hi <= n) v = false;
    add(v, lo != null ? "owner_occupancy" : "units", `not an owner-occupied building of ${n} units or fewer`);
  }
  const vs = reasons.map((r) => r.verdict);
  if (vs.includes(false)) return { verdict: false as boolean | null, missing: [] as string[], reasons };
  if (vs.includes(null)) {
    const missing = [...new Set(reasons.filter((r) => r.verdict === null && r.fact).map((r) => r.fact as string))].sort();
    return { verdict: null as boolean | null, missing, reasons };
  }
  return { verdict: true as boolean | null, missing: [] as string[], reasons };
}

export function statusOn(rule: Rule, asOf: string): "applies" | "not_yet_effective" | "pending" | null {
  if (rule.status === "failed") return null;
  if (rule.status === "pending") return "pending";
  const eff = rule.effective_date;
  if (eff && (eff + "-01-01".slice(eff.length - 4)).slice(0, 10) > asOf) return "not_yet_effective";
  if (rule.status === "not_yet_effective" && !eff) return "not_yet_effective";
  return "applies";
}

const isCap = (r: Rule) => !!r.sets_limit && !!r.key_value;
const LIVE: Result[] = ["applies", "unknown", "not_yet_effective", "pending"];

export function lookup(addr: { state: string; legal_city: string | null }, rules: Rule[], asOf: string, f: Facts): Row[] {
  const stack = [addr.state, ...(addr.legal_city ? [addr.legal_city] : [])];
  const out = new Map<string, Row & { rule: Rule }>();
  for (const rule of rules) {
    if (!stack.includes(rule.jurisdiction)) continue;
    const status = statusOn(rule, asOf);
    if (status === null) continue;
    const cov = evaluateCoverage(rule.coverage_conditions, f, asOf);
    if (cov.verdict === false) continue;
    out.set(rule.team_rule_id, {
      rule_id: rule.team_rule_id, rule,
      result: cov.verdict === null && status === "applies" ? "unknown" : status,
      missing_facts: cov.verdict === null ? cov.missing : [], reasons: cov.reasons,
      conflict_flag: false, conflict_with: [], superseded_by: null,
    });
  }
  const supersede = (loser: Row, winner: Row) => { loser.result = "superseded"; loser.superseded_by = winner.rule_id; loser.missing_facts = []; };
  // precedence 1: explicit overrides extracted from the law text
  for (const res of out.values())
    if (res.result === "applies")
      for (const oid of (res.rule.overrides as string[] | null) ?? []) {
        const o = out.get(oid);
        if (o && (o.result === "applies" || o.result === "unknown")) supersede(o, res);
      }
  // precedence 2: a local rent cap that applies governs the state rent cap
  for (const res of out.values()) {
    const r = res.rule;
    if (res.result === "applies" && r.level === "city" && r.category === "rent_increase_limits" && isCap(r))
      for (const o of out.values())
        if (o.rule.level === "state" && o.rule.category === r.category && isCap(o.rule) && (o.result === "applies" || o.result === "unknown"))
          supersede(o, res);
  }
  // conflicts, per address: a state rule that preempts local law meets a local rule of the same category
  for (const res of out.values()) {
    const r = res.rule;
    if (r.preempts_local && LIVE.includes(res.result)) {
      for (const o of out.values())
        if (o.rule.level === "city" && o.rule.category === r.category && LIVE.includes(o.result)) {
          res.conflict_flag = o.conflict_flag = true;
          res.conflict_with.push(o.rule.citation);
          o.conflict_with.push(r.citation);
        }
    } else if (r.conflict_flag && !r.preempts_local) {
      res.conflict_flag = true;
      res.conflict_with.push("another published value or date for this rule");
    }
  }
  return [...out.values()].map(({ rule: _r, ...row }) => row);
}
```

---

## Round 2 · Home + address report (the core of the demo)

```
Round 2 of 6: the home page and the address report. This is the heart of the demo; make it excellent before anything else.

HOME (/)
Not a marketing hero. A research tool's front page, left-aligned:
- H1 (Newsreader, 44px desktop / 32px mobile): "Which rental laws apply to this building, on this date?"
- One sentence below (ink-2): "Search one of 500 buildings in California, New Jersey and Massachusetts. Every answer cites the law word for word, and says unknown when the records can't settle it."
- A large search field (Command-style combobox, keyboard: "/" focuses it, arrows + Enter select). Matches street, postal city, legal city, ZIP, id. Each suggestion: street in Plex Sans 500, then "Legal city · Year built · Units" in ink-3 mono. Max 8 suggestions.
- Under it, "Try these" as a compact list (not cards): the 5 entries of data.demo, each "street, legal city" + the "why" text in ink-2. Click opens the report.
- A thin stats line in mono, separated by middle dots: stats.rules rules · stats.quotes_verified/stats.rules quotes verified · stats.addresses buildings · 3 states · 10 cities · stats.postal_city_corrected mailing cities corrected to the legal city.
- A two-column "How an answer is built" section (left: 4 numbered steps in text; right: a small hairline diagram of the chain Address → Legal city (Census) → Rules for the state + city → Conditions checked against the building → Result with quote). Steps: 1 "We place the building in its legal city, not its mailing city." 2 "We collect every rule for that state and city, extracted from official texts with the quote checked word for word." 3 "We check each rule's conditions (year built, units, owner-occupied) against the building's records." 4 "If a fact is missing, the answer is unknown, and we tell you which fact settles it."

ADDRESS REPORT (/address/$id, search params ?asOf=YYYY-MM-DD&role=)
Desktop: two columns. Left (320px, sticky): the building. Right: the answers.

Left column, "Building":
- Street (Newsreader 24px), then "Legal city: Boston, MA" and, if postal_city differs, "Mailing city: South Boston" with an info tooltip "Laws follow city limits, not mailing addresses. Placed with the U.S. Census geocoder." If legal_city_source is postal_fallback, say "Placed by mailing city (geocoder found no match), lower confidence".
- Facts table (label / value / source): Year built, Units (show ranges as "5 or more", "7 to 30"), Use, County, ZIP. Source column in ink-3: source_dataset for supplied values, "Inferred from use code: <use_description>" for units_source use_code, "Not in records" for unknown. Never write "county records" generically.
- Jurisdiction stack: two stacked hairline boxes "State: Massachusetts" and "City: Boston", with the count of rules from each.
- "As of" control: a date input (any date) plus 4 preset chips from as_of_dates labeled: "Dec 31, 2025", "Jan 2, 2026", "Oct 1, 2026 (reference date)", "Jul 2, 2027". If the chosen date is one of as_of_dates, use precomputed results; otherwise run engine.lookup. Same output either way.
- "What changes for this building": a vertical mini timeline of every date in the next and previous 24 months where a rule covering this building starts (effective_date), each with StatusTag and citation. Clicking a date sets the as-of date.

Right column, "Answers":
- Header line: "As of Oct 1, 2026 · 17 rules found · 2 unknown · 1 possible conflict" (mono numbers), and the disclaimer in ink-3.
- Summary strip "Key numbers here": up to 4 key_value facts pulled from rules whose result is applies, one per category in this priority: rent_increase_limits, security_deposits, application_screening_fees, just_cause_eviction. Each shows the key value large (Plex Mono 20px), the category label and citation small. If the rent cap is superseded, show the governing one.
- Then one section per category (the 6, in role order, see Round 3; for now this order: rent increases, eviction protections, security deposits, application fees, tenant screening, algorithmic rent setting). Section header: category label + count. If no rule: "No rule in our sources for <category> at this address." and, if the state has watchlist items in that category, "See what's being proposed" linking to /radar.
- Each rule is a row (not a card): StatusTag, title (Plex Sans 500), one-line requirement (clamped to 2 lines, "More" expands), key_value in mono if present, citation in mono ink-2 with level badge "State" / "City", effective date. Superseded rows are collapsed under the rule that governs them ("Also covers this building, but superseded by <citation>"). Conflict rows show the red TriangleAlert line and the conflicting citation(s) from conflict_with.
- Click a row (or "Show source") to open the Evidence drawer (Sheet from the right, 520px; full screen on mobile):
  1. Result + one sentence why, built from engine reasons: e.g. "Applies: building is built before 1978-10-01 (1927), at least 2 units (32)."
  2. "Checked against this building": each reason as a line with CircleCheck / CircleX / CircleHelp, the condition, the building's value and its source.
  3. "The law says" : quoted_span as a blockquote in Newsreader 17px, with a left 2px --brand rule, and "Quoted word for word from <source_doc_id>".
  4. Citation (mono), "Open official source" (source_url, new tab), "Retrieved <retrieved_at>", effective date, exemptions (if any), penalty (if any), conflict_note (if any), review_status note if to_review.
  5. Copy button "Copy citation" (citation + quote + URL + retrieved date + as-of date) for letters and filings.

UNKNOWN IS AN ANSWER (the feature we want judges to remember)
- Unknown rows get an inline panel under them: "Depends on: <fact label>. <why if CO/exact date>. Where to find it: <where>." followed by the matching input:
  year_built: number input "Year built" + button "Check with this year"
  certificate_of_occupancy_date / exact_construction_date: "Was it issued before <cutoff, formatted>?" Yes / No / Not sure (sets facts.built_before[cutoffIso])
  units: number input "Number of units"
  owner_occupancy: "Does the owner live in the building?" Yes / No / Not sure
- One answer re-runs engine.lookup for the whole building with the user facts (facts are shared across rows, so one year settles every row that needed it). Rows whose result changed get a small "Updated with your answer, not verified" label and a subtle 1px --brand left border. A bar at the top of the answers shows "Using your answers: year built 1965 · Reset" while any user fact is set.
- At the top of the answers, if there are unknowns: "2 answers depend on 1 missing fact: year built." with a link that scrolls to the first one.

States: loading skeleton with hairline blocks (no spinners); unknown id → "We don't have this address in the sample" + search.

Done when: A0001 shows the LA rent ordinance applying and the state cap superseded under it; A0036 shows Mailing city South Boston / Legal city Boston; A0106 shows unknown with year built, and typing 1965 updates the rows with the "not verified" label; A0008 at Oct 1, 2026 shows the NJ FAIR Act as From Jul 1, 2027 with the conflict line, and switching to Jul 2, 2027 flips it to Applies; every row opens the evidence drawer with the verbatim quote.
```

---

## Round 3 · Role lenses + "Heads-up: what's coming"

```
Round 3 of 6: role lenses on the report, and the heads-up panel about upcoming legislation.

ROLE LENSES (same verdicts, different reading). Switching role never changes a result.
- renter: heading "Your protections at this address". Category order: rent increases, eviction protections, security deposits, application fees, tenant screening, algorithmic rent setting. Unknown panels phrased "Ask your landlord or check: <where>". Action button "Print a one-page summary" (print stylesheet: building, as-of date, key numbers, each applying rule with citation and source URL, disclaimer; no nav).
- landlord: heading "Your obligations at this building". Order: rent increases, algorithmic rent setting, eviction protections, security deposits, application fees, tenant screening. Shows a "Compliance checklist" above the sections: one checkbox line per applying rule with its key_value and effective date (local state only, not saved). Upcoming effective dates are highlighted ("Starts Jul 1, 2027: prepare now"). Action "Export CSV" (rule, result, key value, citation, source URL, as-of).
- legislator: heading "Which laws reach this building, and where they collide". Order: algorithmic rent setting, rent increases, eviction protections, then the rest. Conflicts and superseded rules are expanded by default. Shows "Pending in this state" (count from radar) linking to /radar.
- public: heading "What our sources show for this address". Shows the facts provenance table expanded and a "Data gaps here" box listing each missing fact, how many answers it blocks, where to get it.

HEADS-UP: WHAT'S COMING (panel at the bottom of the report, and full page /radar)
Purpose: warn people early about legislation that is coming, ranked by how certain it is. Data: radar.items for the building's state and legal city (+ radar.legend).
- Panel title "Coming up for this building", subtitle "Ranked by certainty. Only items marked Verified come from our checked sources; the rest come from bill and council trackers and are not law."
- Group by certainty, most certain first, with a 5-step certainty meter (5 small squares filled by level: scheduled 5, enacted/adopted 4, verified_pending/moving 3, stalled 2, signal 1) and the legend text. Hide items with in_scope false unless the user clicks "Show related housing items (<n>)".
- Each item: title, citation/bill id in mono, kind (Bill, Ordinance, Resolution, Hearing...), status, categories as small text tags, last action date and "x days ago", "Verified" tag (if verified) or the item's warning text in ink-3 italic directly below it (never hidden behind a click), link "Open on the legislature / council site".
- Role phrasing for the panel subtitle: renter "Laws that could change your rights soon", landlord "Changes to plan for", legislator "Bills moving in your state and city", public "Signals to monitor".
- If council_monitoring for the city is not "monitored", show its text ("No public API for this council: check ...") so we are honest about blind spots.
- /radar page: filters (state, city, category, certainty, verified only), a table sorted by certainty then recency, the same warnings inline, and a "Did not pass" section from radar.closed.

Done when: the role switch reorders sections and rewrites headings without changing any result; A0008 radar shows the NJ FAIR Act as Scheduled (Verified) at the top and unverified NJ bills below with their warnings; A0036 (Boston) shows MA pending algorithmic bills and Boston council items; print preview of the renter summary fits on one page.
```

---

## Round 4 · Portfolio (landlords) and Changes (legislators)

```
Round 4 of 6: two views over many buildings.

PORTFOLIO (/portfolio), for landlords and property managers (RealPage's customers)
- Pick buildings: filters by state and legal city, a "Select all shown" checkbox, and per-row checkboxes; selection kept in the URL.
- Summary bar for the selection at the chosen as-of date: buildings, rules that apply, answers unknown (and the top missing fact), possible conflicts, buildings where algorithmic rent setting is restricted now, and buildings where it becomes restricted later (from not_yet_effective rows) with the date.
- Main table (sticky header, sortable): building, legal city, year built, units, governing rent cap (key_value of the applying rent_increase_limits rule, or "None in our sources"), algorithmic pricing ("Restricted now" / "Restricted from <date>" / "Bill pending" / "No rule found"), unknown count with the missing facts, conflicts, link "Open report".
- "Upcoming for this portfolio": a horizontal timeline of effective dates in the next 24 months with how many selected buildings each one reaches (e.g. "Jul 1, 2027 · NJ FAIR Act · 140 buildings").
- Export CSV of the table (one line per building x rule, with citation, source URL and as-of date).

CHANGES (/changes), for legislators and staff: what a change in law does to real buildings
- One section per change test T1 to T5 (data.changes): title, type, expected behavior, our result line from notes, and a before/after comparison: two columns "Before (as_of_before)" and "After (as_of_after)" with counts per result (applies / unknown / not yet effective / pending), computed from results or engine.lookup for the rule ids in rule_mapping.
- Affected buildings: count + a list grouped by legal city (collapsed, "Show 140 buildings"), each linking to the report at the "after" date. Conflict-flagged buildings listed separately with the conflicting citations (T3).
- T2 is a boundary test: show the two cities side by side ("Hoboken: 40 buildings, HOB rule only · Jersey City: 50 buildings, JC rule only · Newark: none").
- T5: show the notes honestly (if the failed record is missing, say "Open: failed ballot measure not yet in our sources").
- Below the tests: "Coverage gaps by state": for the selected state, the categories where the state has no rule but some of its cities do, and vice versa.

Done when: the portfolio of all Jersey City buildings shows algorithmic pricing "Restricted now" and the FAIR Act on the timeline; CSV downloads open in a spreadsheet with correct columns; /changes shows T1 flipping 250 buildings and T3's 140 buildings with 90 conflicts.
```

---

## Round 5 · Coverage + Method (public office, and the judges' page)

```
Round 5 of 6: the coverage page and the method page.

COVERAGE (/coverage), for public offices
- Matrix: 13 jurisdictions (rows, states in bold with their cities indented under them) x 6 categories (columns). Each cell: count of rules and the dominant status (StatusTag icon only, with tooltip), or "None" in ink-3. Click a cell: side sheet listing the rules (title, citation, status, effective date) linking to the evidence.
- "Fix the data, settle the answers": a table from data.unknowns: city, missing fact (label), answers it blocks, where to get it. Sorted by answers. Above it, one sentence computed from the top row, e.g. "Adding year built for San Diego would settle 150 answers."
- "Flagged for human review": every rule with conflict_flag or conflict_note, and every address-level conflict pair (from results at the reference date), with both citations.
- "Known open questions" (static list, keep the wording): "Berkeley algorithmic ban: effective date", "New Jersey FAIR Act: does it preempt Jersey City and Hoboken?", "Los Angeles RSO: date of the increase formula", "California screening-fee cap: current dollar figure". Each with a one-line note "Shown as a conflict or flagged rule where it appears".

METHOD (/method), the page a judge reads in 60 seconds
- Left-aligned long-form page (max 720px text column, Newsreader headings), sections:
  1. "What it does" (2 sentences).
  2. "How an answer is built" (same 4 steps as home, plus: "Code decides, the language model only extracts. Coverage, dates and precedence are deterministic code, run identically in our pipeline and in this page (parity checked on every answer).").
  3. "Numbers" as a definition list in mono, all from data.stats: rules extracted, quotes verified word for word (x/x), source documents used, documents with text, extra official documents, buildings, geocoded, mailing cities corrected, year built known, units known (supplied + from use code), answers at the reference date by result.
  4. "What we don't do": no legal advice; no guessing (unknown); no rules written by hand; ZIP and mailing city never used to decide which laws apply; bills and council items are signals, not law.
  5. "Limits": owner occupancy is never in the records; certificate-of-occupancy dates are not in the records; some local texts are links only in the challenge pack; watchlist items are not reviewed by a human.
  6. "Reproduce it": the repo command `make all` and the pipeline steps enrich → extract → engine → changes → app bundle.

Done when: the matrix shows MA rent increases as one rule (the statewide ban on local rent control, c. 40P) and nothing for Boston or Cambridge, NJ with the FAIR Act as not yet effective, Hoboken and Jersey City algorithmic rules; the fix-the-data table starts with San Diego / year built / 150; every number on /method matches data.stats.
```

---

## Round 6 · Languages, mobile, polish, QA

```
Round 6 of 6: languages, mobile and a full polish pass. No new features.

LANGUAGES: EN (default), ES, FR. Translate all UI text (nav, headings, buttons, labels, fact labels, where-to-find, status words, legends, empty states, disclaimer, role headings). Keep in English, with the line "Legal text is shown in the original English": rule titles, requirement, quoted_span, exemptions, penalty, citations, bill titles. Language in the URL (?lang=) and localStorage. Dates formatted per language (Oct 1, 2026 / 1 oct 2026 / 1 oct. 2026).

MOBILE (375px wide): report columns stack (Building first, collapsible), evidence drawer full screen, tables become stacked rows with labels, matrix scrolls horizontally inside its own container with the first column sticky, no horizontal page scroll, 44px touch targets.

POLISH PASS: consistent spacing on the 8px grid; one H1 per page; every icon button has an aria-label; focus ring visible; no layout shift on load; StatusTag used for every status; numbers in mono; no lorem ipsum, no "TODO", no console errors. Page titles: "<page> · Covenant".

QA: open each demo address at each preset date and each role; check /qa still says 0 mismatches. List anything that failed.

Done when: the app reads well in ES and FR with legal text untouched; the report works one-handed on a phone; /qa is 0 mismatches.
```

---

## Optional rounds (only if everything above is green before 05:00)

**Round 7 · Any address (outside the 500).** A TanStack server function calls the free U.S. Census geocoder (`https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress`, params `benchmark=Public_AR_Current&vintage=Current_Current&layers=Incorporated Places,Counties,States&format=json`, no key) and returns state + legal city. Outside CA/NJ/MA: "Not covered: our sources cover CA, NJ and MA only." Inside a covered state but not one of the 10 cities: "Only state rules are covered here; local rules may be missing." Then engine.lookup with all building facts unknown, and the Unknown panels ask the user for them, every user fact labeled "not verified".

**Round 8 · Ask about this report (grounded Q&A).** A chat box in the report that can only use the rules currently shown (their requirement, key_value, quoted_span, citation, result and as-of date). Use Lovable AI on the server. System prompt: answer only from the given rules; every sentence ends with the rule citation it relies on; if the rules don't answer the question, reply exactly "Our sources for this building don't answer that." Validate the reply in code: if it cites a citation that isn't in the context, replace it with that fallback sentence. Show the disclaimer under every answer.
