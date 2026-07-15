.PHONY: help install dev lint format typecheck test test-verbose build clean publish-test release-patch release-minor release-major tag align-version demo demo-stdio demo-http demo-headless demo-record demo-clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Setup ────────────────────────────────────────────────────────────────────

install: ## Install package in production mode
	pip install -e .

dev: ## Install package with dev dependencies
	pip install -e ".[dev]" ruff mypy types-PyYAML

# ─── Quality ──────────────────────────────────────────────────────────────────

lint: ## Run ruff linter
	ruff check fastauthmcp/ tests/ examples/

format: ## Format code with ruff
	ruff format fastauthmcp/ tests/ examples/

format-check: ## Check formatting without changing files
	ruff format --check fastauthmcp/ tests/ examples/

typecheck: ## Run mypy type checking
	mypy fastauthmcp/ --ignore-missing-imports

check: lint format-check typecheck ## Run all checks (lint + format + types)

# ─── Testing ──────────────────────────────────────────────────────────────────

test: ## Run tests
	pytest -v --tb=short

test-verbose: ## Run tests with full output
	pytest -v --tb=long -s

# ─── Build & Publish ─────────────────────────────────────────────────────────

build: clean ## Build sdist and wheel
	python -m build

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info fastauthmcp/*.egg-info

publish-test: build ## Publish to TestPyPI
	twine upload --repository testpypi dist/*

# ─── Demo ─────────────────────────────────────────────────────────────────────

demo: ## Run E2E demo (stdio, browser login)
	./scripts/demo.sh stdio

demo-sse: ## Run E2E demo (SSE, browser login)
	./scripts/demo.sh sse

demo-http: ## Run E2E demo (streamable-http, browser login)
	./scripts/demo.sh http

demo-headless: ## Show headless token-exchange architecture
	./scripts/demo-headless.sh explain

demo-record: ## Record demo GIF (requires: brew install vhs)
	./scripts/record-demo.sh

demo-clean: ## Remove demo virtualenv
	./scripts/demo.sh clean

# ─── Versioning & Release ────────────────────────────────────────────────────

VERSION := $(shell grep '^version' pyproject.toml | head -1 | sed 's/version = "\(.*\)"/\1/')

version: ## Show current version
	@echo $(VERSION)

release-patch: ## Bump patch version, commit, and tag
	@$(MAKE) _release BUMP=patch

release-minor: ## Bump minor version, commit, and tag
	@$(MAKE) _release BUMP=minor

release-major: ## Bump major version, commit, and tag
	@$(MAKE) _release BUMP=major

_release:
	@CURRENT=$(VERSION); \
	IFS='.' read -r MAJOR MINOR PATCH <<< "$$CURRENT"; \
	case "$(BUMP)" in \
		patch) NEW="$$MAJOR.$$MINOR.$$((PATCH + 1))";; \
		minor) NEW="$$MAJOR.$$((MINOR + 1)).0";; \
		major) NEW="$$((MAJOR + 1)).0.0";; \
	esac; \
	echo "Bumping $$CURRENT → $$NEW ($(BUMP))"; \
	sed -i '' "s/version = \"$$CURRENT\"/version = \"$$NEW\"/" pyproject.toml; \
	git add pyproject.toml; \
	git commit -m "release: v$$NEW"; \
	git tag -a "v$$NEW" -m "Release v$$NEW"; \
	echo "Done. Run 'git push origin main && git push origin v$$NEW' to publish."

tag: ## Create a tag from the current pyproject.toml version
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	@echo "Tag v$(VERSION) created. Run 'git push origin v$(VERSION)' to trigger publish."

align-version: ## Force-move the latest v* tag to match pyproject.toml version
	@echo "Aligning tag v$(VERSION) to current HEAD..."
	git tag -f "v$(VERSION)"
	@echo "Run 'git push origin v$(VERSION) --force' to update remote."
