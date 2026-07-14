"""Pet Store MCP Server — A sample HTTP-style API served via Ceramic.

A simple pet store with CRUD operations, protected by Ceramic's full
middleware pipeline (authentication, observability, sessions).

Usage:
    # stdio transport (default)
    python petstore_server.py

    # SSE transport
    CERAMIC_TRANSPORT=sse python petstore_server.py

    # Streamable HTTP transport
    CERAMIC_TRANSPORT=streamable-http python petstore_server.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from ceramic import FastMCP, identity

# ---------------------------------------------------------------------------
# In-memory pet store database
# ---------------------------------------------------------------------------

_pets_db: dict[str, dict[str, Any]] = {
    "pet-001": {
        "id": "pet-001",
        "name": "Luna",
        "species": "cat",
        "breed": "Maine Coon",
        "age": 3,
        "status": "available",
        "added_by": "store@petstore.example",
        "added_at": "2024-11-01T09:00:00Z",
    },
    "pet-002": {
        "id": "pet-002",
        "name": "Rex",
        "species": "dog",
        "breed": "German Shepherd",
        "age": 5,
        "status": "adopted",
        "added_by": "store@petstore.example",
        "added_at": "2024-10-15T14:30:00Z",
    },
    "pet-003": {
        "id": "pet-003",
        "name": "Nemo",
        "species": "fish",
        "breed": "Clownfish",
        "age": 1,
        "status": "available",
        "added_by": "store@petstore.example",
        "added_at": "2024-12-10T11:00:00Z",
    },
}

_next_id = 4

# ---------------------------------------------------------------------------
# Ceramic MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("petstore", config="ceramic.yaml")


@mcp.tool()
def whoami() -> dict[str, Any]:
    """Show the current authenticated user's identity."""
    user = identity()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": sorted(user.roles),
        "groups": sorted(user.groups),
    }


@mcp.tool()
def list_pets(status: str | None = None) -> list[dict[str, Any]]:
    """List all pets in the store. Optionally filter by status.

    Args:
        status: Filter by status ("available" or "adopted"). Omit for all.
    """
    identity()  # Ensure caller is authenticated
    pets = list(_pets_db.values())
    if status:
        pets = [p for p in pets if p["status"] == status]
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "species": p["species"],
            "status": p["status"],
        }
        for p in pets
    ]


@mcp.tool()
def get_pet(pet_id: str) -> dict[str, Any]:
    """Get full details of a specific pet.

    Args:
        pet_id: The pet ID (e.g., "pet-001")
    """
    if pet_id not in _pets_db:
        return {"error": "not_found", "message": f"Pet {pet_id} not found"}
    return _pets_db[pet_id]


@mcp.tool()
def add_pet(name: str, species: str, breed: str, age: int) -> dict[str, Any]:
    """Add a new pet to the store.

    Args:
        name: Pet name
        species: Species (cat, dog, fish, bird, etc.)
        breed: Breed name
        age: Age in years
    """
    global _next_id
    user = identity()

    pet_id = f"pet-{_next_id:03d}"
    _next_id += 1

    pet = {
        "id": pet_id,
        "name": name,
        "species": species,
        "breed": breed,
        "age": age,
        "status": "available",
        "added_by": user.email,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    _pets_db[pet_id] = pet
    return {"created": pet}


@mcp.tool()
def update_pet_status(pet_id: str, status: str) -> dict[str, Any]:
    """Update a pet's availability status.

    Args:
        pet_id: The pet ID
        status: New status ("available" or "adopted")
    """
    if pet_id not in _pets_db:
        return {"error": "not_found", "message": f"Pet {pet_id} not found"}

    valid = {"available", "adopted"}
    if status not in valid:
        return {
            "error": "invalid_status",
            "message": f"Status must be one of: {', '.join(sorted(valid))}",
        }

    old_status = _pets_db[pet_id]["status"]
    _pets_db[pet_id]["status"] = status
    return {
        "updated": {
            "id": pet_id,
            "name": _pets_db[pet_id]["name"],
            "old_status": old_status,
            "new_status": status,
        }
    }


@mcp.tool()
def delete_pet(pet_id: str) -> dict[str, Any]:
    """Remove a pet from the store permanently.

    Args:
        pet_id: The pet ID to delete
    """
    if pet_id not in _pets_db:
        return {"error": "not_found", "message": f"Pet {pet_id} not found"}

    deleted = _pets_db.pop(pet_id)
    return {"deleted": {"id": pet_id, "name": deleted["name"]}}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging

    log_level = os.environ.get("CERAMIC_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    transport = os.environ.get("CERAMIC_TRANSPORT", "stdio")
    host = os.environ.get("CERAMIC_HOST", "localhost")
    port = int(os.environ.get("CERAMIC_PORT", "8000"))
    mcp.run(transport=transport, host=host, port=port)
