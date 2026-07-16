"""Automatic scenario discovery.

Discovers all Scenario subclasses in fastauthmcp.lab.scenarios.* modules.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastauthmcp.lab.scenario import Scenario


def discover_scenarios() -> list[type["Scenario"]]:
    """Import all scenario modules and collect Scenario subclasses."""
    from fastauthmcp.lab import scenarios as scenarios_pkg
    from fastauthmcp.lab.scenario import Scenario

    found: list[type[Scenario]] = []

    for importer, modname, ispkg in pkgutil.walk_packages(
        scenarios_pkg.__path__, prefix=scenarios_pkg.__name__ + "."
    ):
        try:
            module = importlib.import_module(modname)
        except Exception:
            continue

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, Scenario)
                and attr is not Scenario
                and not getattr(attr, "__abstract__", False)
            ):
                found.append(attr)

    return found
