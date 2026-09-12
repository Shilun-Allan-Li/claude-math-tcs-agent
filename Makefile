PLUGIN := plugins/math-tcs
MARKET := /Users/rxw/Desktop/projects/research/claude-math-tcs-agent
TARGET ?= $(HOME)/Desktop/projects/research/tcslib

.PHONY: validate test test-lean dev install update uninstall demo-run clean-target

validate:            ## validate plugin + marketplace manifests strictly
	claude plugin validate $(PLUGIN) --strict
	claude plugin validate . --strict

test:                ## unit tests (no Lean)
	cd $(PLUGIN)/tests && python3 -m pytest -q -m "not lean"

test-lean:           ## Lean-backed tests against $(TARGET)
	cd $(PLUGIN)/tests && MATH_TCS_TEST_PROJECT=$(TARGET) python3 -m pytest -q -m lean

dev:                 ## start Claude Code in the target with the plugin loaded from this checkout
	cd $(TARGET) && claude --plugin-dir $(MARKET)/$(PLUGIN)

install:             ## persistent install (user scope) from this checkout as a local marketplace
	claude plugin marketplace add $(MARKET) || true
	claude plugin install math-tcs@math-tcs-local --scope user

update:              ## after bumping version in both manifests
	claude plugin marketplace update math-tcs-local
	claude plugin update math-tcs@math-tcs-local

uninstall:
	claude plugin uninstall math-tcs@math-tcs-local

clean-target:        ## remove demo artifacts from the target (keeps config)
	rm -rf $(TARGET)/math-tcs/scratch $(TARGET)/math-tcs/locks $(TARGET)/math-tcs/context
