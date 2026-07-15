## Summary

Brief description of what this PR does.

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior)
- [ ] Documentation update
- [ ] Refactoring (no functional change)
- [ ] CI/CD or tooling change

## Related Issues

Closes #

## Changes

- 
- 
- 

## How to Test

Steps to verify this change:

1. 
2. 
3. 

## Checklist

### General
- [ ] Code follows the project style (ruff check + ruff format pass)
- [ ] Type annotations on all new public functions
- [ ] Docstrings on all new public classes/functions
- [ ] CHANGELOG.md updated under `[Unreleased]` (if user-facing)

### Testing
- [ ] Unit tests added/updated
- [ ] Property-based tests added (if security-sensitive)
- [ ] All tests pass (`pytest -v`)
- [ ] No real HTTP calls in tests (mocked or test utilities used)

### Security (if touching auth, tokens, or IDP communication)
- [ ] Read `.ai/security.md` before making changes
- [ ] No tokens/secrets logged
- [ ] TLS enforcement preserved
- [ ] Circuit breaker protection preserved
- [ ] Relevant ADR read and respected

### Architecture
- [ ] Public API (`fastauthmcp/__init__.py`) unchanged (or ADR written)
- [ ] Middleware execution order preserved
- [ ] No new dependencies without justification in PR description
- [ ] Configuration changes have defaults (backward compatible)

## Screenshots / Logs (if applicable)

## Additional Notes

Anything reviewers should know.
