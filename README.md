# Deep State · Hack-Nation 7th Global AI Hackathon

Team **Deep State** at the [Hack-Nation 7th Global AI Hackathon](https://hack-nation.ai/hackathon) (Oct 3-4, 2026).

## Key times (ET)
- **Sat Oct 3, 12:00 PM**: global kick-off, challenges revealed
- **Sun Oct 4, 9:00 AM**: submission deadline (hard)
- Oct 8: finalists notified · Oct 10: finalist pitches and awards

## Challenge
_TBD at kick-off: track, problem statement, judging criteria._

## Idea
_TBD._

## Team
| Name | Role | GitHub |
|------|------|--------|
| Solal Abitbol | | @solal24 |
| | | |

## Repo layout
```
src/        application / model code
notebooks/  exploration
data/       local data (git-ignored, share download scripts instead)
docs/       pitch deck, demo video link, submission text
```

## Setup
```bash
git clone https://github.com/solal24/hack-nation-deep-state.git
cd hack-nation-deep-state
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your own API keys, never commit .env
```

## Working together
- Pull before you start, commit small and often, push regularly
- One branch per feature (`git checkout -b feat/<name>`), merge to `main` via PR or quick review
- `main` must always run: the demo is built from it
- Never commit API keys: put them in `.env`

## Submission checklist
- [ ] Working demo
- [ ] Demo video (link in `docs/`)
- [ ] Pitch / slides
- [ ] README updated with problem, solution, how to run
- [ ] Submitted before Sun 9:00 AM ET
