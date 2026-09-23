PLUGIN := plugins/math-tcs
MARKET := $(CURDIR)
TARGET ?=
TARGET_ABS = $(shell cd "$(TARGET)" 2>/dev/null && pwd)
.DEFAULT_GOAL := validate

.PHONY: validate test test-lean dev install update uninstall demo-run clean-target require-target

require-target:
	@test -n "$(TARGET)" && test -f "$(TARGET_ABS)/lean-toolchain" || { echo 'Set TARGET to an existing Lean project, e.g. make dev TARGET="/path/to/project"' >&2; exit 1; }

validate:            ## validate plugin + marketplace manifests strictly
	claude plugin validate $(PLUGIN) --strict
	claude plugin validate . --strict

test:                ## unit tests (no Lean)
	cd $(PLUGIN)/tests && python3 -m pytest -q -m "not lean"

test-lean: require-target  ## Lean-backed tests against an explicitly chosen project
	cd "$(PLUGIN)/tests" && MATH_TCS_TEST_PROJECT="$(TARGET_ABS)" python3 -m pytest -q -m lean

dev: require-target   ## start Claude Code in the target with this checkout loaded
	cd "$(TARGET_ABS)" && claude --plugin-dir "$(MARKET)/$(PLUGIN)"

install:             ## persistent install (user scope) from this checkout as a local marketplace
	claude plugin marketplace add "$(MARKET)"
	claude plugin install math-tcs@math-tcs-local --scope user

update:              ## after bumping version in both manifests
	claude plugin marketplace update math-tcs-local
	claude plugin update math-tcs@math-tcs-local

uninstall:
	claude plugin uninstall math-tcs@math-tcs-local

clean-target: require-target  ## remove legacy demo artifacts from the chosen target
	rm -rf "$(TARGET_ABS)/math-tcs/scratch" "$(TARGET_ABS)/math-tcs/locks" "$(TARGET_ABS)/math-tcs/context"
