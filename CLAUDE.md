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
| Elie Abou-Fadel | eaboufadel3 | _TBD_ |
| Ismail Ameur | IsmaA24 | _TBD_ |

Only edit files owned by your human unless they ask otherwise. If you must touch shared files (`src/llm.py`, `requirements.txt`, this file), keep the change minimal and mention it in the commit message.

## Partners (use them, judges notice)
- **Lovable**: AI app builder (React + Supabase). Use it for the user-facing app
- **Wajo AI / Fo**: agent that books, buys, pays, calls, emails. Use it for the real-world action in the demo
- **ElevenLabs** (credits + own challenge, TBD): voice, TTS, voice agents that can place phone calls via API
- **Bright Data** (credits): web scraping / unblocking / SERP API / ready-made scrapers. Use it to get real data instead of synthetic

## Stack
- Frontend: Lovable app (lives in its own Lovable-synced GitHub repo, link it here once created)
- Backend: Python 3.11+ in this repo (ML / optimization), exposed as a small API if Lovable needs it
- Fallback UI: `streamlit run src/app.py` if Lovable blocks us
- LLM calls go through `src/llm.py` (`ask`, `ask_json`). Model set by `CLAUDE_MODEL` in `.env`
- Keys live in `.env` only (copy `.env.example`). Never commit `.env`, never hardcode keys

## Rules for Claude
- `main` must always run. Work on a branch `feat/<name>`, merge only when it runs
- Always `git pull` before starting work; commit small, push often
- Prefer the simplest thing that demos well. No premature abstractions, no test suites unless asked
- Never add data files to git (`data/` is ignored); add a download script instead
- Before the deadline, priority order: demo works > README explains it > code is clean
- Update the "Challenge", "Our idea" and "Team" sections when the team decides
