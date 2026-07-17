"""Chat engine — connects LLM to MCP tools via FastAuthMCP.

Handles:
- LLM API calls (OpenAI-compatible)
- Tool execution through FastAuthMCP middleware
- Streaming responses back to the UI
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from fastauthmcp.lab.ui.scenarios import ScenarioConfig
from fastauthmcp.testing import FastAuthMCPTestClient

logger = logging.getLogger(__name__)


# ─── Tool definitions exposed to the LLM ─────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "whoami",
            "description": "Show the current authenticated user's identity (email, roles, groups).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_pets",
            "description": "List all pets in the pet store. Optionally filter by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: 'available' or 'adopted'",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pet",
            "description": "Get full details of a specific pet by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pet_id": {"type": "string", "description": "The pet ID (e.g. pet-001)"}
                },
                "required": ["pet_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_pet",
            "description": "Add a new pet to the store.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "species": {"type": "string"},
                    "breed": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "required": ["name", "species", "breed", "age"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "admin_action",
            "description": "Perform an admin-only action. Requires 'admin' role.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ─── MCP Server emulation ────────────────────────────────────────────────────


def _create_mcp_server():
    """Create a FastAuthMCP server with sample tools for the lab."""
    from fastauthmcp import FastMCP, identity

    mcp = FastMCP(name="lab-ui-server")

    _pets_db = {
        "pet-001": {
            "id": "pet-001",
            "name": "Luna",
            "species": "cat",
            "breed": "Maine Coon",
            "age": 3,
            "status": "available",
        },
        "pet-002": {
            "id": "pet-002",
            "name": "Rex",
            "species": "dog",
            "breed": "German Shepherd",
            "age": 5,
            "status": "adopted",
        },
        "pet-003": {
            "id": "pet-003",
            "name": "Nemo",
            "species": "fish",
            "breed": "Clownfish",
            "age": 1,
            "status": "available",
        },
    }

    @mcp.tool()
    def whoami() -> dict:
        user = identity()
        return {
            "subject": user.subject,
            "email": user.email,
            "roles": sorted(user.roles),
            "groups": sorted(user.groups),
        }

    @mcp.tool()
    def list_pets(status: str | None = None) -> list:
        identity()
        pets = list(_pets_db.values())
        if status:
            pets = [p for p in pets if p["status"] == status]
        return [
            {"id": p["id"], "name": p["name"], "species": p["species"], "status": p["status"]}
            for p in pets
        ]

    @mcp.tool()
    def get_pet(pet_id: str) -> dict:
        identity()
        if pet_id not in _pets_db:
            return {"error": "not_found", "message": f"Pet {pet_id} not found"}
        return _pets_db[pet_id]

    @mcp.tool()
    def add_pet(name: str, species: str, breed: str, age: int) -> dict:
        user = identity()
        pet_id = f"pet-{len(_pets_db) + 1:03d}"
        pet = {
            "id": pet_id,
            "name": name,
            "species": species,
            "breed": breed,
            "age": age,
            "status": "available",
            "added_by": user.email,
        }
        _pets_db[pet_id] = pet
        return {"created": pet}

    @mcp.tool()
    def admin_action() -> dict:
        user = identity()
        if "admin" not in user.roles:
            return {"error": "forbidden", "message": "Admin role required"}
        return {"action": "completed", "by": user.email}

    return mcp


# ─── Chat Engine ──────────────────────────────────────────────────────────────


class ChatEngine:
    """Connects LLM API to MCP tools via FastAuthMCP."""

    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o",
        api_key: str = "",
        base_url: str | None = None,
        scenario: ScenarioConfig | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._scenario = scenario
        self._mcp_server = _create_mcp_server()
        self._messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant with access to an MCP server. "
                    "Use the available tools to answer user questions. "
                    "Always call tools when appropriate rather than guessing."
                ),
            }
        ]

    async def chat(self, user_message: str) -> AsyncIterator[dict[str, Any]]:
        """Send a message and yield response events (text, tool_call, tool_result, error)."""
        if not self._api_key:
            yield {
                "type": "error",
                "content": "No API key configured. Enter your key in the left panel.",
            }
            return

        self._messages.append({"role": "user", "content": user_message})

        # Filter tools based on scenario
        tools = TOOL_DEFINITIONS
        if self._scenario:
            available = set(self._scenario.tools)
            tools = [
                t
                for t in TOOL_DEFINITIONS
                if t["function"]["name"] in available  # type: ignore[index]
            ]

        # Call LLM
        try:
            response = await self._call_llm(tools)
        except Exception as exc:
            yield {"type": "error", "content": f"LLM API error: {exc}"}
            return

        message = response.get("choices", [{}])[0].get("message", {})

        # Handle tool calls
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            self._messages.append(message)

            for tc in tool_calls:
                func = tc.get("function", {})
                name = func.get("name", "unknown")
                args_str = func.get("arguments", "{}")

                yield {"type": "tool_call", "name": name, "args": args_str}

                # Execute tool via FastAuthMCP
                result = await self._execute_tool(name, args_str)
                result_str = json.dumps(result) if isinstance(result, (dict, list)) else str(result)

                yield {"type": "tool_result", "content": result_str}

                self._messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": result_str,
                    }
                )

            # Get final response after tool calls
            try:
                final_response = await self._call_llm([])
                final_message = final_response.get("choices", [{}])[0].get("message", {})
                content = final_message.get("content", "")
                if content:
                    self._messages.append({"role": "assistant", "content": content})
                    yield {"type": "text", "content": content}
            except Exception as exc:
                yield {"type": "error", "content": f"LLM follow-up error: {exc}"}
        else:
            # Plain text response
            content = message.get("content", "")
            if content:
                self._messages.append({"role": "assistant", "content": content})
                yield {"type": "text", "content": content}

    async def _call_llm(self, tools: list[dict]) -> dict:
        """Make an OpenAI-compatible API call."""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        # Provider-specific headers
        if self._provider == "anthropic":
            headers["x-api-key"] = self._api_key
            headers["anthropic-version"] = "2023-06-01"
            del headers["Authorization"]

        body: dict[str, Any] = {
            "model": self._model,
            "messages": self._messages,
        }
        if tools:
            body["tools"] = tools

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self._base_url}/chat/completions",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def _execute_tool(self, name: str, args_json: str) -> Any:
        """Execute an MCP tool through FastAuthMCP middleware."""
        try:
            args = json.loads(args_json) if args_json else {}
        except json.JSONDecodeError:
            args = {}

        # Create a test client with the scenario's identity
        identity_kwargs: dict[str, Any] = {}
        if self._scenario:
            identity_kwargs = {
                "email": self._scenario.identity.get("email"),
                "subject": self._scenario.identity.get("sub"),
                "roles": self._scenario.identity.get("roles", []),
                "groups": self._scenario.identity.get("groups", []),
            }
        else:
            identity_kwargs = {
                "email": "anonymous@lab.test",
                "subject": "anonymous",
                "roles": [],
                "groups": [],
            }

        client = FastAuthMCPTestClient(self._mcp_server, **identity_kwargs)
        return await client.call_tool(name, **args)
