# Method note · Covenant, Rental Housing Law Navigator

Team Deep State (Solal Abitbol, Elie Abou-Fadel, Ismail Ameur) · Hack-Nation 7th Global AI Hackathon · Challenge 2 (RealPage) · Not legal advice.

## What it does
For one building on one date, Covenant says which rental rules apply in six categories, quotes the official text for each, and answers "unknown" when the records cannot settle it, naming the fact that would.

## Approach: the model extracts, code decides
1. **Place the building.** The Census geocoder gives the legal city. We never use the ZIP or the mailing city: 38 of the 500 mailing cities were wrong for this purpose (for example "Dorchester" is Boston). 493 of 500 addresses geocoded; unit counts are known for 467 (257 supplied, 210 read from the building use code).
2. **Extract the rules.** A language model (Claude Sonnet) reads each source document once and fills the supplied rule schema. Every rule keeps the passage it was read from. No rule is written by hand.
3. **Decide coverage.** Plain deterministic code tests each rule against the building (year built, units, owner occupancy) with three outcomes: true, false, unknown. It then applies start dates and precedence: a local rent cap governs the state cap, and a state law that may preempt a local one is flagged as a possible conflict, per address.
4. **Explain.** Each answer carries its result, citation, quoted passage, source link, retrieval date and as-of date.

## Verification
- **Quotes: 88 of 88** rule passages are found word for word in their source document. A rule whose quote is not found is rejected.
- **Change tests T1 to T5** behave as described in the brief: T1 250 buildings switch on Jan 1, 2026 · T2 Hoboken 40, Jersey City 50, Newark 0 · T3 140 buildings, 90 conflict flags · T4 110 buildings, pending only · T5 the ballot measure is recorded as failed and no rent cap applies in Massachusetts.
- **Same engine in the pipeline and in the app.** The app's engine is a port of the Python engine; a check page compares both on every answer for all 500 buildings (0 mismatches at the last run).
- **Reproducible.** `make all` rebuilds the three output files. Model answers are cached, so a rerun costs nothing and gives the same result.

## Results at the reference date (Oct 1, 2026)
88 rules (84 in force, 2 pending, 1 not yet effective, 1 failed) from 48 documents. 8,541 answers over 500 buildings: 7,164 apply, 819 unknown, 220 pending, 198 superseded, 140 not yet effective. Nearly every unknown depends on the year built, which public records lack for Newark, Berkeley and San Diego.

## Responsible design
- "Unknown" is an answer. The app then asks the reader for the one missing fact and labels the result "not verified".
- Enacted, not yet effective, pending and failed are never merged.
- Bills and council items (LegiScan, Open States, Legistar) appear only under "Coming up", ranked by certainty and marked "not reviewed".
- Every screen says "not legal advice". The app states facts and quotes the law; it never says an act is legal or illegal.

## Limits
- **Sources outside the starter pack.** 33 of the 87 supplied documents are links without text. We added 11 official texts (Jersey City, Hoboken and Newark ordinances, the Massachusetts court ruling, San Diego's enacted code). The 14 rules from them are labeled in the data and in the app; T2, T3 and T5 depend on them.
- 56 of 88 rules do not record a start date; we assume they were already in force at the reference date.
- Owner occupancy and certificate-of-occupancy dates are not in any public record we use.
- Only some unit conditions are machine-checkable (18 of 88 rules).
- No lawyer reviewed the output.

## Scaling path
A new jurisdiction needs its official texts and a parcel source. One command ingests a document end to end (`make ingest DOC=...`): extraction, quote check, engine, affected buildings. The live lookup already answers for any address in the ten cities from public parcel records.
