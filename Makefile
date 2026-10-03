PY ?= .venv/bin/python

.PHONY: setup enrich extract engine changes eval all ingest online online-check

setup:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

enrich:        ## 0 · geocode + use-code parsing -> data/addresses_enriched.csv
	$(PY) -m pipeline.enrich

extract:       ## 1 · corpus -> outputs/rules.json (verified spans)
	$(PY) -m pipeline.extract

engine:        ## 2 · rules x addresses -> outputs/coverage.json, outputs/lookups.json
	$(PY) -m pipeline.engine

changes:       ## 3 · T1-T5 -> outputs/changes.json
	$(PY) -m pipeline.changes

eval:          ## 4 · checks + gold set report
	$(PY) -m eval.run

all: enrich extract engine changes eval

ingest:        ## add one new document end to end: make ingest DOC=path/to/doc.txt
	$(PY) -m pipeline.extract --doc $(DOC) && $(MAKE) engine changes eval

online:        ## external data: one address outside the sample -> data/addresses_online.csv (make online ADDR="...")
	$(PY) -m pipeline.online_address "$(ADDR)"

online-check:  ## accuracy of the online lookup vs the supplied sample (10 addresses per city)
	$(PY) -m pipeline.online_address --validate 10
