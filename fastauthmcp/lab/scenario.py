"""Base scenario class.

All lab test scenarios inherit from this.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioTrace:
    """Trace information captured during a scenario run."""

    identity: dict[str, Any] = field(default_factory=dict)
    claims: dict[str, Any] = field(default_factory=dict)
    authorization: dict[str, Any] = field(default_factory=dict)
    result: Any = None


class Scenario(ABC):
    """Base class for all compatibility lab scenarios.

    Subclass this and implement `run()`. Optionally override `setup()` and
    `teardown()` for resource management.

    Attributes:
        name: Machine-readable scenario name (becomes documentation).
        category: Grouping category (authentication, authorization, security, mcp_protocol).
        description: Human-readable description shown in reports.
        provider_name: Which identity provider this tests against.

    Example:
        class AdminAccessGranted(Scenario):
            name = "admin_role_grants_access"
            category = "authorization"
            description = "Admin role → admin_action tool succeeds"

            async def run(self):
                ...
    """

    name: str = "unnamed"
    category: str = "general"
    description: str = ""
    provider_name: str = "mock"

    def __init__(self) -> None:
        self.trace = ScenarioTrace()

    async def setup(self) -> None:
        """Prepare resources (providers, servers, etc). Override as needed."""
        pass

    @abstractmethod
    async def run(self) -> None:
        """Execute the scenario. Raise on failure."""
        ...

    async def teardown(self) -> None:
        """Clean up resources. Override as needed."""
        pass
