"""Reporting: terminal summary and HTML report generation."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastauthmcp.lab.runner.engine import ScenarioResult


def print_summary(results: list["ScenarioResult"]) -> None:
    """Print a terminal summary of results."""
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total_ms = sum(r.duration_ms for r in results)

    print("  ═══════════════════════════════════════════")
    print(f"  Result: {passed} passed, {failed} failed ({total_ms:.0f}ms)")

    if failed:
        print()
        print("  Failures:")
        for r in results:
            if not r.passed:
                desc = r.description or r.name
                print(f"    ✗ {desc}")
                print(f"      {r.error}")

    print()


def generate_html_report(results: list["ScenarioResult"]) -> None:
    """Generate an HTML report at ./reports/index.html."""
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Group by category
    by_category: dict[str, list] = defaultdict(list)
    for r in results:
        by_category[r.category].append(r)

    category_labels = {
        "authentication": "Authentication",
        "authorization": "Authorization",
        "security": "Security",
        "mcp_protocol": "MCP Protocol",
        "identity": "Identity Propagation",
        "general": "General",
    }

    sections = ""
    for cat_key in [
        "authentication",
        "authorization",
        "security",
        "identity",
        "mcp_protocol",
        "general",
    ]:
        if cat_key not in by_category:
            continue
        label = category_labels.get(cat_key, cat_key.title())
        rows = ""
        for r in by_category[cat_key]:
            status = "✓" if r.passed else "✗"
            status_class = "pass" if r.passed else "fail"
            desc = r.description or r.name
            error_cell = f'<span class="error">{r.error}</span>' if r.error else ""
            trace_html = ""
            if r.trace and r.passed:
                trace_items = []
                for k, v in r.trace.items():
                    if k == "traceback":
                        continue
                    trace_items.append(f"<code>{k}: {v}</code>")
                if trace_items:
                    trace_html = "<br>".join(trace_items)

            rows += f"""
            <tr class="{status_class}">
                <td class="status">{status}</td>
                <td>
                    <div class="desc">{desc}</div>
                    <div class="provider">{r.provider_name}</div>
                    {f'<div class="trace">{trace_html}</div>' if trace_html else ""}
                    {error_cell}
                </td>
                <td class="duration">{r.duration_ms:.0f}ms</td>
            </tr>"""

        sections += f"""
        <section>
            <h2>{label}</h2>
            <table>{rows}</table>
        </section>"""

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>FastAuthMCP Security & Interoperability Lab</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', system-ui, sans-serif; background: #0d1117; color: #e6edf3; padding: 2rem; }}
h1 {{ color: #58a6ff; margin-bottom: 0.5rem; }}
.subtitle {{ color: #8b949e; margin-bottom: 2rem; }}
.summary {{ padding: 1rem 1.5rem; background: #161b22; border-radius: 8px; margin-bottom: 2rem;
    border-left: 4px solid {"#3fb950" if failed == 0 else "#f85149"}; }}
.summary strong {{ font-size: 1.1rem; }}
section {{ margin-bottom: 2rem; }}
h2 {{ color: #c9d1d9; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.05em;
    padding-bottom: 0.5rem; border-bottom: 1px solid #30363d; margin-bottom: 0.5rem; }}
table {{ width: 100%; border-collapse: collapse; }}
tr {{ border-bottom: 1px solid #21262d; }}
td {{ padding: 0.6rem 0.5rem; vertical-align: top; }}
.status {{ width: 2rem; font-size: 1.1rem; }}
.duration {{ width: 4rem; color: #8b949e; text-align: right; font-size: 0.85rem; }}
.desc {{ font-weight: 500; }}
.provider {{ color: #8b949e; font-size: 0.8rem; }}
.trace {{ color: #8b949e; font-size: 0.75rem; margin-top: 0.3rem; }}
.trace code {{ background: #161b22; padding: 0.1rem 0.3rem; border-radius: 3px; }}
.error {{ color: #f85149; font-size: 0.8rem; margin-top: 0.3rem; display: block; }}
.pass .status {{ color: #3fb950; }}
.fail .status {{ color: #f85149; }}
.timestamp {{ color: #484f58; font-size: 0.8rem; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>FastAuthMCP Security & Interoperability Lab</h1>
<p class="subtitle">Compatibility report — {len(results)} scenarios</p>

<div class="summary">
    <strong>{passed} passed</strong> &nbsp; <strong>{failed} failed</strong>
</div>

{sections}

<p class="timestamp">Generated: {timestamp}</p>
</body>
</html>"""

    report_path = report_dir / "index.html"
    report_path.write_text(html)
    print(f"  Report: {report_path}")
