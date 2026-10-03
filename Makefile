PY ?= .venv/bin/python
# Which sources go into the OFFICIAL outputs/rules.json: "starter" (RealPage corpus only, default: CLAUDE.md
# keeps corpus_extra out unless organizers allow it) or "all" (starter + corpus_extra).
# outputs/rules_all.json always has everything; corpus_extra rules there carry review_status "to_review".
SOURCES ?= starter

.PHONY: setup enrich extract engine changes eval all ingest online online-check external answer-check

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

online:        ## external data: one address outside the sample -> data/addresses_online.csv (make online ADDR="...")
	$(PY) -m pipeline.online_address "$(ADDR)"

online-check:  ## accuracy of the online lookup vs the supplied sample (10 addresses per city)
	$(PY) -m pipeline.online_address --validate 10

external:      ## external data: state bills (LegiScan + Open States), council items (Legistar), enacted bill texts -> data/external/
	$(PY) -m pipeline.legislation && $(PY) -m pipeline.council && $(PY) -m pipeline.bill_texts

answer-check:  ## answer(): 7 self-tests (sample, public data, user facts, 4 out-of-scope reasons) + warning check
	$(PY) -m pipeline.answer --selftest
