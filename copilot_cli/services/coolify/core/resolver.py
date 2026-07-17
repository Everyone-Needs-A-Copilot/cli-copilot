"""Smart resource resolver — find resources by name, domain, or IP instead of UUID."""

from __future__ import annotations

import re
import time
from typing import Any

# Simple in-memory cache: {resource_type: (timestamp, data)}
_cache: dict[str, tuple[float, list[dict]]] = {}
CACHE_TTL = 60.0  # seconds


def _is_uuid(query: str) -> bool:
    """Check if a string looks like a Coolify UUID or standard UUID."""
    if re.match(r"^[a-z0-9]{20,}$", query, re.IGNORECASE):
        return True
    if re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        query,
        re.IGNORECASE,
    ):
        return True
    return False


def _get_cached(resource_type: str) -> list[dict] | None:
    """Get cached resource list if still valid."""
    if resource_type in _cache:
        ts, data = _cache[resource_type]
        if time.time() - ts < CACHE_TTL:
            return data
    return None


def _set_cache(resource_type: str, data: list[dict]) -> None:
    """Cache a resource list."""
    _cache[resource_type] = (time.time(), data)


def clear_cache() -> None:
    """Clear the resolver cache."""
    _cache.clear()


async def resolve_application(client: Any, query: str) -> str:
    """Resolve an application query to UUID.

    Searches by UUID, name, or FQDN (domain).
    """
    from copilot_cli.services.coolify.core.exceptions import (
        AmbiguousMatchError,
        ResourceNotFoundError,
    )

    if _is_uuid(query):
        return query

    cached = _get_cached("applications")
    if cached is not None:
        apps = cached
    else:
        apps = await client.list_applications()
        _set_cache("applications", apps)

    query_lower = query.lower()
    matches = [
        app
        for app in apps
        if query_lower in (app.get("name") or "").lower()
        or query_lower in (app.get("fqdn") or "").lower()
    ]

    if len(matches) == 0:
        all_names = [app.get("name", "") for app in apps if app.get("name")]
        raise ResourceNotFoundError("application", query, _suggestions(query, all_names))
    if len(matches) > 1:
        match_names = [f"{m.get('name', '?')} ({m.get('fqdn', 'no domain')})" for m in matches]
        raise AmbiguousMatchError("application", query, match_names)

    return matches[0]["uuid"]


async def resolve_server(client: Any, query: str) -> str:
    """Resolve a server query to UUID.

    Searches by UUID, name, or IP address.
    """
    from copilot_cli.services.coolify.core.exceptions import (
        AmbiguousMatchError,
        ResourceNotFoundError,
    )

    if _is_uuid(query):
        return query

    cached = _get_cached("servers")
    if cached is not None:
        servers = cached
    else:
        servers = await client.list_servers()
        _set_cache("servers", servers)

    query_lower = query.lower()
    matches = [
        s
        for s in servers
        if query_lower in (s.get("name") or "").lower()
        or query_lower in (s.get("ip") or "").lower()
    ]

    if len(matches) == 0:
        all_names = [s.get("name", "") for s in servers if s.get("name")]
        raise ResourceNotFoundError("server", query, _suggestions(query, all_names))
    if len(matches) > 1:
        match_names = [f"{m.get('name', '?')} ({m.get('ip', '?')})" for m in matches]
        raise AmbiguousMatchError("server", query, match_names)

    return matches[0]["uuid"]


async def resolve_database(client: Any, query: str) -> str:
    """Resolve a database query to UUID."""
    from copilot_cli.services.coolify.core.exceptions import (
        AmbiguousMatchError,
        ResourceNotFoundError,
    )

    if _is_uuid(query):
        return query

    cached = _get_cached("databases")
    if cached is not None:
        dbs = cached
    else:
        dbs = await client.list_databases()
        _set_cache("databases", dbs)

    query_lower = query.lower()
    matches = [db for db in dbs if query_lower in (db.get("name") or "").lower()]

    if len(matches) == 0:
        all_names = [db.get("name", "") for db in dbs if db.get("name")]
        raise ResourceNotFoundError("database", query, _suggestions(query, all_names))
    if len(matches) > 1:
        match_names = [
            f"{m.get('name', '?')} ({m.get('type') or m.get('database_type', '?')})"
            for m in matches
        ]
        raise AmbiguousMatchError("database", query, match_names)

    return matches[0]["uuid"]


async def resolve_service(client: Any, query: str) -> str:
    """Resolve a service query to UUID."""
    from copilot_cli.services.coolify.core.exceptions import (
        AmbiguousMatchError,
        ResourceNotFoundError,
    )

    if _is_uuid(query):
        return query

    cached = _get_cached("services")
    if cached is not None:
        services = cached
    else:
        services = await client.list_services()
        _set_cache("services", services)

    query_lower = query.lower()
    matches = [svc for svc in services if query_lower in (svc.get("name") or "").lower()]

    if len(matches) == 0:
        all_names = [svc.get("name", "") for svc in services if svc.get("name")]
        raise ResourceNotFoundError("service", query, _suggestions(query, all_names))
    if len(matches) > 1:
        match_names = [f"{m.get('name', '?')} ({m.get('type', '?')})" for m in matches]
        raise AmbiguousMatchError("service", query, match_names)

    return matches[0]["uuid"]


async def resolve_project(client: Any, query: str) -> str:
    """Resolve a project query to UUID."""
    from copilot_cli.services.coolify.core.exceptions import (
        AmbiguousMatchError,
        ResourceNotFoundError,
    )

    if _is_uuid(query):
        return query

    cached = _get_cached("projects")
    if cached is not None:
        projects = cached
    else:
        projects = await client.list_projects()
        _set_cache("projects", projects)

    query_lower = query.lower()
    matches = [p for p in projects if query_lower in (p.get("name") or "").lower()]

    if len(matches) == 0:
        all_names = [p.get("name", "") for p in projects if p.get("name")]
        raise ResourceNotFoundError("project", query, _suggestions(query, all_names))
    if len(matches) > 1:
        match_names = [m.get("name", "?") for m in matches]
        raise AmbiguousMatchError("project", query, match_names)

    return matches[0]["uuid"]


def _suggestions(query: str, names: list[str], max_suggestions: int = 3) -> list[str]:
    """Generate fuzzy suggestions from available names."""
    query_lower = query.lower()
    scored = []
    for name in names:
        name_lower = name.lower()
        # Simple scoring: shared character ratio
        common = sum(1 for c in query_lower if c in name_lower)
        score = common / max(len(query_lower), 1)
        if score > 0.3:
            scored.append((score, name))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [name for _, name in scored[:max_suggestions]]
