# Contributing to FastAuthMCP Framework

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/fastauthmcp.git
cd fastauthmcp

# Install in dev mode
pip install -e ".[dev]"

# Verify everything works
pytest
```

## Making Changes

1. Create a branch from `main`:
   ```bash
   git checkout -b feature/your-feature
   ```

2. Make your changes and add tests.

3. Run the test suite:
   ```bash
   pytest -v
   ```

4. Commit with a clear message:
   ```bash
   git commit -m "Add support for X"
   ```

5. Push and open a Pull Request.

## Code Style

- Python 3.11+ features (union types with `|`, `match` statements, etc.)
- Type annotations on all public functions
- Docstrings on all public classes and functions
- Tests for all new functionality

## Testing

We use a dual testing strategy:

- **Property-based tests** (Hypothesis) in `tests/properties/` — verify universal properties
- **Unit tests** (pytest) in `tests/unit/` — cover specific examples and edge cases
- **Integration tests** in `tests/integration/` — end-to-end with mocked services

Run specific test categories:
```bash
pytest tests/unit/           # Unit tests only
pytest tests/properties/     # Property tests only
pytest tests/integration/    # Integration tests only
```

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Include tests for new behavior
- Update documentation if you change public APIs
- All CI checks must pass before merge
- Update CHANGELOG.md under `[Unreleased]` for user-facing changes

### Commit Conventions

Use clear, imperative commit messages:

```
feat: add Redis session backend
fix: prevent token refresh race condition
docs: update token exchange configuration guide
refactor: extract PKCE helpers into separate module
test: add property tests for circuit breaker state machine
ci: add dependency audit to security workflow
```

Prefix categories: `feat`, `fix`, `docs`, `refactor`, `test`, `ci`, `chore`

### PR Requirements

1. **Title**: Short, imperative (`Add X`, `Fix Y`, not `Added X` or `Fixing Y`)
2. **Description**: What changed, why, how to test
3. **Tests**: Every PR must include tests (unit minimum, property-based for security)
4. **Lint**: `ruff check` and `ruff format --check` must pass
5. **Types**: `mypy fastauthmcp/ --ignore-missing-imports` must pass
6. **No network in tests**: All HTTP mocked via pytest-mock or test utilities
7. **Backward compatible**: Config changes must have defaults; public API preserved

### Security-Sensitive Changes

Changes to auth, tokens, TLS, or identity require:
- Reading `.ai/security.md` before starting
- Tests for rejection/failure cases (not just happy path)
- Property-based tests for invariants (e.g., "redactor never leaks secrets")
- Explicit mention in PR description of security implications

## Reporting Issues

- Use GitHub Issues with the appropriate template
- Include: Python version, OS, fastauthmcp version, steps to reproduce
- A minimal reproducing example is appreciated
- For security vulnerabilities: use GitHub Security Advisories (private), NOT public issues

## Architecture

FastAuthMCP uses composition (not inheritance) over FastMCP. The key architectural principles:

1. **FastAuthMCP** holds a `FastMCP` instance as a private delegate
2. **Middleware pipeline** intercepts requests before/after FastMCP handling
3. **Configuration-driven** — features activate based on `fastauthmcp.yaml` sections
4. **contextvars** propagate request-scoped state (identity, session, trace)

See `.kiro/specs/fastauthmcp-framework/design.md` for the full design document.

## Dependency & Compatibility Testing

FastAuthMCP uses `>=` lower-bound pins (e.g., `fastmcp>=2.0.0`) to maximize compatibility. Our CI validates against:

- **Python 3.11, 3.12, and 3.13** on every push and PR
- **Latest versions** of all dependencies (installed fresh in CI)
- **Security audit** via `pip-audit` on a weekly schedule and on every PR

If you add or bump a dependency:
1. Use `>=` with the minimum version you've tested against
2. Run `pip-audit` locally to check for known vulnerabilities: `pip install pip-audit && pip-audit`
3. Document in your PR description why the dependency is needed and the minimum version chosen
4. The Compatibility Lab (`make lab`) exercises integration points with mocked IdP responses to catch regressions
