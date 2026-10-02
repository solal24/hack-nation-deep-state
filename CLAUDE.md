# CLAUDE.md · Team Deep State

Shared context for every teammate's Claude. Keep it short and up to date.

## Event
Hack-Nation 7th Global AI Hackathon. 24h build. **Submission deadline: Sun Oct 4, 9:00 AM ET (hard).**
Judges value a working demo above everything: a polished narrow feature beats a broken ambitious one.

## Challenge
_TBD at kick-off (Sat 12:00 PM ET): track, problem statement, judging criteria, sponsor tools required._

## Our idea
_TBD._

## Team and ownership
| Person | GitHub | Owns |
|--------|--------|------|
| Solal | solal24 | _TBD_ (available from Sat ~6:30 PM ET) |
| | eaboufadel3 | _TBD_ |
| Isma | IsmaA24 | _TBD_ |

Only edit files owned by your human unless they ask otherwise. If you must touch shared files (`src/llm.py`, `requirements.txt`, this file), keep the change minimal and mention it in the commit message.

## Stack
- Python 3.11+, `streamlit` for the demo UI (`streamlit run src/app.py`)
- LLM calls go through `src/llm.py` (`ask`, `ask_json`). Model set by `CLAUDE_MODEL` in `.env`
- Keys live in `.env` only (copy `.env.example`). Never commit `.env`, never hardcode keys

## Rules for Claude
- `main` must always run. Work on a branch `feat/<name>`, merge only when it runs
- Always `git pull` before starting work; commit small, push often
- Prefer the simplest thing that demos well. No premature abstractions, no test suites unless asked
- Never add data files to git (`data/` is ignored); add a download script instead
- Before the deadline, priority order: demo works > README explains it > code is clean
- Update the "Challenge", "Our idea" and "Team" sections when the team decides
