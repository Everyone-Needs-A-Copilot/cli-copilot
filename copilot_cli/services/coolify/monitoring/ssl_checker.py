"""SSL certificate expiry checking."""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse


@dataclass
class SSLResult:
    domain: str = ""
    valid: bool = False
    issuer: str = ""
    subject: str = ""
    expires: str = ""
    days_remaining: int = 0
    error: str = ""


def check_ssl(domain: str, port: int = 443, timeout: float = 10.0) -> SSLResult:
    """Check SSL certificate for a domain."""
    result = SSLResult(domain=domain)

    # Strip protocol and path
    if "://" in domain:
        parsed = urlparse(domain)
        domain = parsed.hostname or domain
    domain = domain.split("/")[0].split(":")[0]

    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                if not cert:
                    result.error = "No certificate returned"
                    return result

                # Parse expiry
                expires_str = cert.get("notAfter", "")
                if expires_str:
                    expires_dt = datetime.strptime(expires_str, "%b %d %H:%M:%S %Y %Z")
                    expires_dt = expires_dt.replace(tzinfo=UTC)
                    now = datetime.now(UTC)
                    delta = expires_dt - now
                    result.expires = expires_dt.isoformat()
                    result.days_remaining = delta.days
                    result.valid = delta.days > 0

                # Parse issuer and subject
                issuer = dict(x[0] for x in cert.get("issuer", []))
                subject = dict(x[0] for x in cert.get("subject", []))
                result.issuer = issuer.get("organizationName", issuer.get("commonName", ""))
                result.subject = subject.get("commonName", "")
    except ssl.SSLCertVerificationError as e:
        result.error = f"SSL verification failed: {e}"
    except TimeoutError:
        result.error = "Connection timed out"
    except socket.gaierror:
        result.error = "DNS resolution failed"
    except Exception as e:
        result.error = str(e)

    return result


def check_ssl_batch(domains: list[str], warn_days: int = 30) -> list[SSLResult]:
    """Check SSL for multiple domains."""
    results: list[SSLResult] = []
    for domain in domains:
        result = check_ssl(domain)
        results.append(result)
    return results
