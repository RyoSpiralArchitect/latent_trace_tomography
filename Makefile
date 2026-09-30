PYTHON ?= python3

.PHONY: lint test preflight design-summary smoke check

lint:
	PYTHONPATH=src $(PYTHON) -m ruff check src tests
	PYTHONPATH=src $(PYTHON) -m ruff format --check src tests

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

preflight:
	PYTHONPATH=src $(PYTHON) -S -m latent_trace_tomography preflight \
		--protocol protocols/oss_reliance_regime_v0/protocol.json

design-summary:
	PYTHONPATH=src $(PYTHON) -S -m latent_trace_tomography oss-design-summary

smoke:
	@smoke_root=$$(mktemp -d); \
	PYTHONPATH=src $(PYTHON) -S -m latent_trace_tomography synthetic-demo \
		--out-dir "$$smoke_root/run" \
		--seed 7

check: lint test preflight design-summary smoke
