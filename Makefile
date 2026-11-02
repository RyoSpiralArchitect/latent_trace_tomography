PYTHON ?= python3
CHECKPOINT_PATHS = reports/mistral_bridge_20261029 successors/oss_reliance_regime_v0/answer_mapping_probe_v1 reports/gpt6luna_answer_mapping_20261031 successors/oss_reliance_regime_v0/output_contract_probe_v1
CONTRACT_SCORING = successors/oss_reliance_regime_v0/output_contract_scoring_v1
WEAK_CHECKPOINT = reports/weak_projection_checkpoint_20261102
SCALED_CHECKPOINT = reports/scaled_reference_screen_20261102

.PHONY: lint test preflight design-summary smoke check

lint:
	PYTHONPATH=src $(PYTHON) -m ruff check src tests $(CHECKPOINT_PATHS) $(CONTRACT_SCORING) $(WEAK_CHECKPOINT) $(SCALED_CHECKPOINT)
	PYTHONPATH=src $(PYTHON) -m ruff format --check src tests $(CHECKPOINT_PATHS) $(CONTRACT_SCORING) $(WEAK_CHECKPOINT) $(SCALED_CHECKPOINT)

test:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -S -m unittest discover -s reports/mistral_bridge_20261029 -v
	$(PYTHON) -S -m unittest discover -s successors/oss_reliance_regime_v0/answer_mapping_probe_v1 -v
	$(PYTHON) -S -m unittest discover -s reports/gpt6luna_answer_mapping_20261031 -v
	$(PYTHON) -S -m unittest discover -s successors/oss_reliance_regime_v0/output_contract_probe_v1 -v
	$(PYTHON) -S -m unittest discover -s $(CONTRACT_SCORING) -v
	$(PYTHON) -S -m unittest discover -s $(WEAK_CHECKPOINT) -v
	$(PYTHON) -S -m unittest discover -s $(SCALED_CHECKPOINT) -v

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
