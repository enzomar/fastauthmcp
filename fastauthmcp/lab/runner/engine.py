"""Lab execution engine.

Discovers scenarios, runs them grouped by category, generates reports.
"""

from __future__ import annotations

import asyncio
import sys
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from fastauthmcp.lab.runner.discovery import discover_scenarios
from fastauthmcp.lab.runner.reporting import generate_html_report, print_summary


@dataclass
class ScenarioResult:
    """Result of a single scenario execution."""

    name: str
    category: str
    description: str
    provider_name: str
    passed: bool
    duration_ms: float
    error: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)


# Category display order and labels
CATEGORY_LABELS = {
    "authentication": "Authentication",
    "authorization": "Authorization",
    "security": "Security",
    "mcp_protocol": "MCP Protocol",
    "identity": "Identity Propagation",
    "general": "General",
}


def main() -> int:
    """CLI entry point. Returns exit code."""
    args = sys.argv[1:]
    if not args or args[0] == "run":
        return asyncio.run(_run_all())
    elif args[0] == "list":
        return _list_scenarios()
    else:
        print("Usage: python -m fastauthmcp.lab [run|list]")
        return 1


def _list_scenarios() -> int:
    """List all discovered scenarios grouped by category."""
    scenarios = discover_scenarios()

    print()
    print("  FastAuthMCP Security & Interoperability Lab")
    print("  ═══════════════════════════════════════════")
    print()

    # Group by category
    by_category: dict[str, list] = defaultdict(list)
    for cls in sorted(scenarios, key=lambda s: (s.category, s.name)):
        by_category[cls.category].append(cls)

    # Print compatibility matrix
    print("  Compatibility Matrix")
    print()

    # Provider summary
    providers = sorted(set(cls.provider_name for cls in scenarios))
    print("  OIDC Providers ───────────────")
    for p in ["mock", "zitadel", "keycloak", "auth0", "azure", "okta"]:
        label = {
            "mock": "Generic OIDC (Mock)",
            "zitadel": "ZITADEL",
            "keycloak": "Keycloak",
            "auth0": "Auth0",
            "azure": "Azure Entra ID",
            "okta": "Okta",
        }.get(p, p)
        if p in providers:
            print(f"    ✓ {label}")
        else:
            print(f"    ○ {label}")

    print()
    print("  Scenarios ────────────────────")
    print()

    for category_key in [
        "authentication",
        "authorization",
        "security",
        "identity",
        "mcp_protocol",
        "general",
    ]:
        if category_key not in by_category:
            continue
        label = CATEGORY_LABELS.get(category_key, category_key.title())
        print(f"    {label}")
        for cls in by_category[category_key]:
            desc = cls.description or cls.name
            print(f"      • {desc}")
        print()

    print(f"  Total: {len(scenarios)} scenarios")
    print()
    return 0


async def _run_all() -> int:
    """Discover and run all scenarios."""
    print()
    print("  ╔══════════════════════════════════════════════════════════════╗")
    print("  ║      FastAuthMCP Security & Interoperability Lab            ║")
    print("  ╚══════════════════════════════════════════════════════════════╝")
    print()

    print("  Discovering scenarios...")
    scenario_classes = discover_scenarios()
    print(f"  Found {len(scenario_classes)} scenarios")
    print()

    if not scenario_classes:
        print("  No scenarios found.")
        return 0

    # Group by category
    by_category: dict[str, list] = defaultdict(list)
    for cls in sorted(scenario_classes, key=lambda s: (s.category, s.name)):
        by_category[cls.category].append(cls)

    results: list[ScenarioResult] = []

    for category_key in [
        "authentication",
        "authorization",
        "security",
        "identity",
        "mcp_protocol",
        "general",
    ]:
        if category_key not in by_category:
            continue

        label = CATEGORY_LABELS.get(category_key, category_key.title())
        print(f"  {label}")
        print(f"  {'─' * len(label)}")

        for cls in by_category[category_key]:
            scenario = cls()
            start = time.perf_counter()
            try:
                await scenario.setup()
                await scenario.run()
                duration = (time.perf_counter() - start) * 1000

                # Build trace info for display
                trace_info = _format_trace(scenario)
                results.append(
                    ScenarioResult(
                        name=cls.name,
                        category=cls.category,
                        description=cls.description,
                        provider_name=cls.provider_name,
                        passed=True,
                        duration_ms=duration,
                        trace=trace_info,
                    )
                )

                desc = cls.description or cls.name
                print(f"  ✓ {desc}")
                _print_trace(scenario)

            except Exception as exc:
                duration = (time.perf_counter() - start) * 1000
                error_msg = f"{type(exc).__name__}: {exc}"
                results.append(
                    ScenarioResult(
                        name=cls.name,
                        category=cls.category,
                        description=cls.description,
                        provider_name=cls.provider_name,
                        passed=False,
                        duration_ms=duration,
                        error=error_msg,
                        trace={"traceback": traceback.format_exc()},
                    )
                )

                desc = cls.description or cls.name
                print(f"  ✗ {desc}")
                print(f"      {error_msg}")
            finally:
                try:
                    await scenario.teardown()
                except Exception:
                    pass

        print()

    print_summary(results)
    generate_html_report(results)

    failed = sum(1 for r in results if not r.passed)
    return 1 if failed > 0 else 0


def _format_trace(scenario) -> dict[str, Any]:
    """Extract trace info from a completed scenario."""
    trace = scenario.trace
    info: dict[str, Any] = {}
    if trace.identity:
        info["identity"] = trace.identity
    if trace.claims:
        info["claims"] = trace.claims
    if trace.authorization:
        info["authorization"] = trace.authorization
    if trace.result is not None:
        info["result"] = trace.result
    return info


def _print_trace(scenario) -> None:
    """Print trace details for a passed scenario."""
    trace = scenario.trace
    if trace.identity:
        for key, val in trace.identity.items():
            print(f"      {key}: {val}")
    if trace.authorization:
        for key, val in trace.authorization.items():
            if isinstance(val, list):
                print(f"      {key}:")
                for item in val:
                    print(f"        - {item}")
            else:
                print(f"      {key}: {val}")
