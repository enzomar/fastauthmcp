---
inclusion: fileMatch
fileMatchPattern: "ceramic/**/*.py,examples/**/*.py,pyproject.toml,ceramic.yaml.example"
---

# Keep README.md Up to Date

Whenever you modify the public API, add/remove features, change CLI commands, update dependencies, or alter the project structure, you MUST also update `README.md` to reflect those changes.

## What triggers a README update

- Adding or removing a public export from `ceramic/__init__.py`
- Adding or removing a CLI command in `ceramic/cli/`
- Changing the configuration schema in `ceramic/config.py`
- Adding new example files in `examples/`
- Modifying `pyproject.toml` (dependencies, entry points, project metadata)
- Adding new directories to the project structure
- Changing installation instructions or requirements

## What to update in README.md

- **Features table** — if a feature is added or removed
- **Usage examples** — if the API changes
- **CLI section** — if commands are added, removed, or renamed
- **Project structure** — if directories or key files change
- **Installation** — if dependencies or Python version requirements change
- **Configuration Reference** — if `ceramic.yaml.example` changes

## Rules

- Keep the README concise and user-focused
- Update code examples to match the actual current API
- Do not add features to the README that are not yet implemented
- Ensure `pip install ceramic-fwk` and `from ceramic import FastMCP` remain accurate
- If you add a new example in `examples/`, add a brief mention in the README
