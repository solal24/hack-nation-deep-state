PY ?= .venv/bin/python
# Which sources go into the OFFICIAL outputs/rules.json: "all" (starter + corpus_extra) or "starter" (RealPage corpus only).
# outputs/rules_all.json always has everything (for the app).
SOURCES ?= all

.PHONY: setup enrich extract engine changes eval all ingest

setup:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

enrich:        ## 0 · geocode + use-code parsing -> data/addresses_enriched.csv
	$(PY) -W ignore -m pipeline.enrich

extract:       ## 1 · corpus (+ corpus_extra) -> outputs/rules.json + rules_all.json (verified quotes)
	OFFICIAL_SOURCES=$(SOURCES) $(PY) -W ignore -m pipeline.extract

engine:        ## 2 · rules x 500 addresses -> outputs/lookups.json
	$(PY) -W ignore -m pipeline.engine

changes:       ## 3 · T1-T5 -> outputs/changes.json
	$(PY) -W ignore -m pipeline.changes

eval:          ## 4 · checks + gold set report (skipped until eval/run.py exists)
	@if [ -f eval/run.py ]; then $(PY) -W ignore -m eval.run; else echo "eval: not set up yet (eval/run.py missing), skipped"; fi

all: enrich extract engine changes eval

ingest:        ## new documents end to end: make ingest DOC=X001,X002 (other documents' rules are kept)
	OFFICIAL_SOURCES=$(SOURCES) $(PY) -W ignore -m pipeline.extract --doc $(DOC) && $(MAKE) engine changes eval
