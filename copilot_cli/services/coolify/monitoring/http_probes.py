"""Async HTTP health probing for application domains."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx


@dataclass
class ProbeResult:
    url: str = ""
    status_code: int = 0
    response_time_ms: float = 0.0
    healthy: bool = False
    error: str = ""
    redirect_url: str = ""


def public_probe_url(domain: str) -> str:
    """Convert a Coolify FQDN into its public HTTP(S) probe URL.

    Coolify app FQDNs may suffix the internal container port (for example,
    ``https://app.example.com:3000``), while Traefik exposes the route on the
    standard public port. Probing the internal port directly creates a false
    outage report.
    """
    url = domain if domain.startswith(("http://", "https://")) else f"https://{domain}"
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    return urlunsplit((parsed.scheme, hostname, parsed.path, parsed.query, parsed.fragment))


async def probe_url(url: str, timeout: float = 10.0) -> ProbeResult:
    """Probe a single URL for health."""
    result = ProbeResult(url=url)
    try:
        start = time.monotonic()
        async with httpx.AsyncClient(
            follow_redirects=True, verify=False, timeout=timeout
        ) as client:
            response = await client.get(url)
        elapsed = (time.monotonic() - start) * 1000
        result.status_code = response.status_code
        result.response_time_ms = round(elapsed, 1)
        result.healthy = 200 <= response.status_code < 400
        if response.history:
            result.redirect_url = str(response.url)
    except httpx.ConnectError as e:
        result.error = f"Connection failed: {e}"
    except httpx.TimeoutException:
        result.error = "Timeout"
    except Exception as e:
        result.error = str(e)
    return result


async def probe_domains(domains: list[str], timeout: float = 10.0) -> list[ProbeResult]:
    """Probe multiple domains concurrently."""
    urls: list[str] = []
    for domain in domains:
        urls.append(public_probe_url(domain))
    tasks = [probe_url(url, timeout) for url in urls]
    return await asyncio.gather(*tasks)
