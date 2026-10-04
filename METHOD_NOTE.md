# Covenant · Rental Housing Law Navigator · Method note

Team Deep State (Solal Abitbol, Elie Abou-Fadel, Ismail Ameur) · Hack-Nation 7th Global AI Hackathon · Challenge 2 (RealPage) · Code and outputs: github.com/solal24/hack-nation-deep-state · Not legal advice.

**What it does.** For one building on one date, Covenant says which rental rules apply in the six categories, quotes the official text behind each answer, and answers "unknown" when the records cannot settle it, naming the fact that would.

**Principle: the model reads the law, code decides.** A language model is used only to read legal text. Every answer about a building comes from plain, deterministic code, so it can be reproduced and explained.

## Module A · Rule extraction (automated, no rule written by hand)
- **Extract.** Claude Sonnet reads each source document once and fills the supplied rule schema. All 88 rules validate against it.
- **Check the quote.** Code looks for each quoted passage in the source text and keeps the exact excerpt. If it is not found, the rule is rejected and retried once. The extraction log shows 6 rejected candidates, 4 of them because the quote was not in the source.
- **Link coverage.** A city's rent cap often sits on a rates page that does not say which buildings are covered. For 11 such rules, the building conditions come from a sibling rule or a verbatim-checked sentence in the same city's documents, so a cap is not applied to new construction.

## Module B · Address lookup
- **Place.** The Census geocoder gives the legal city, never the ZIP or mailing city: 493 of 500 matched, 38 mailing cities were wrong ("Dorchester" is Boston). Unit counts: 257 supplied, 210 read from the building use code, 1 disagreement kept as a range.
- **Decide.** For each rule of the building's state and city, code tests the conditions (year built, units, owner occupancy) with three outcomes: true, false, unknown. It then applies the rule's status on the as-of date, then precedence (a local rent cap governs the state cap: "superseded"), then flags possible conflicts per address (a state law that may preempt a local one).

## Module C · Change tracking
The engine runs on all 500 addresses at each test's dates. T1: 250 buildings switch on Jan 1, 2026 · T2: Hoboken 40, Jersey City 50, Newark 0 · T3: 140 not yet effective, 90 conflict flags · T4: 110, pending only · T5: recorded as failed, no rent cap in Massachusetts. The app answers any as-of date.

## Results on Oct 1, 2026
88 rules from 48 documents: 84 in force, 2 pending, 1 not yet effective, 1 failed. 8,541 answers over 500 buildings: 7,164 apply, 819 unknown, 220 pending, 198 superseded, 140 not yet effective. 800 of the 819 unknowns wait on the year built, which public records lack mostly in Newark, Berkeley and San Diego.

## How we checked
- **Quotes:** 88 of 88 found word for word in their source. Re-run without the model: `python -m pipeline.extract --verify-only`.
- **Format:** all 88 rules pass the supplied schema. The two other files follow the supplied templates, with a few extra fields.
- **Same engine in the app:** the app runs a TypeScript copy of the engine. Its check page compares it with the pipeline on every answer: 0 mismatches over 34,166 (500 buildings, 4 dates) at the last run.
- No hand-labeled answer set was built, and no lawyer reviewed the output.

## Responsible design
"Unknown" is an answer: the app then asks the reader for the missing fact and marks the result "not verified". Enacted, not yet effective, pending and failed are never merged. Every answer shows its source, quoted text, retrieval date and as-of date. Bills and council items (LegiScan, Open States, Legistar) appear only under "Coming up", marked "not reviewed". Every screen says "not legal advice", and the app never says an act is legal or illegal.

## Limits
- **Texts beyond the supplied ones.** 33 of the 87 supplied documents are links without text. From official public sources of the kind the brief lists (state and municipal codes, plus the Massachusetts court's docket), we added 11 official texts, fetched one page at a time. 6 of them yield 14 of the 88 rules: Jersey City, Hoboken and Newark ordinances, the Massachusetts court ruling, San Diego's enacted code. These rules are labeled in `rules.json` (`provenance`) and in the app. T2, T3 and T5 depend on them.
- 56 of 88 rules record no start date. We treat them as already in force on the reference date.
- 34 rules carry building conditions the engine tests. Conditions it cannot test from building facts are kept as notes for the reader. 17 rules have a confidence below 0.7.
- Owner occupancy and certificate-of-occupancy dates are in no public record we use.

## Reproduce and extend
`make all SOURCES=all` rebuilds the three files. Model answers are cached, so a re-run costs nothing and gives the same result. `make ingest DOC=...` adds one document end to end. Any address in nine cities is answered live from public parcel records, on an exact address match only.
