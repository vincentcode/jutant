"""What every HTTP client for the bank's systems shares: connection settings, auth, TLS,
timeouts, retries, and turning HTTP failures into the adapter errors.

Each system is configured by environment variables under its own prefix, for example
JUTANT_CORE_BANKING_URL, JUTANT_CORE_BANKING_AUTH=bearer and JUTANT_CORE_BANKING_TOKEN.
See `Connection.from_env` for the full list.
"""

import os
import ssl
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast, get_args
from urllib.parse import quote

import httpx

from packs.banking.adapters.base import BankUnavailable, NotFound

AuthKind = Literal["none", "bearer", "basic", "api_key"]


@dataclass(frozen=True)
class Connection:
    base_url: str
    auth: AuthKind = "none"
    token: str = ""  # the bearer token or the API key
    username: str = ""  # basic auth
    password: str = ""
    api_key_header: str = "X-API-Key"
    timeout_s: float = 10.0
    ca_bundle: str = ""  # the bank's own certificate authority, if its TLS uses one
    client_cert: str = ""  # mutual TLS: the certificate and key files this platform presents
    client_key: str = ""

    @classmethod
    def from_env(cls, prefix: str, env: Mapping[str, str] = os.environ) -> "Connection":
        """`<prefix>_URL` (required), `_AUTH` (none, bearer, basic or api_key), `_TOKEN`,
        `_USERNAME`, `_PASSWORD`, `_API_KEY_HEADER`, `_TIMEOUT_S`, `_CA_BUNDLE`,
        `_CLIENT_CERT` and `_CLIENT_KEY`."""

        def get(name: str, default: str = "") -> str:
            return env.get(f"{prefix}_{name}", default).strip()

        if not get("URL"):
            raise ValueError(f"{prefix}_URL is not set")
        auth = get("AUTH", "none").lower()
        if auth not in get_args(AuthKind):
            raise ValueError(f"{prefix}_AUTH must be one of {', '.join(get_args(AuthKind))}")
        connection = cls(
            base_url=get("URL"),
            auth=cast(AuthKind, auth),
            token=get("TOKEN"),
            username=get("USERNAME"),
            password=get("PASSWORD"),
            api_key_header=get("API_KEY_HEADER", "X-API-Key"),
            timeout_s=float(get("TIMEOUT_S", "10")),
            ca_bundle=get("CA_BUNDLE"),
            client_cert=get("CLIENT_CERT"),
            client_key=get("CLIENT_KEY"),
        )
        if auth in ("bearer", "api_key") and not connection.token:
            raise ValueError(f"{prefix}_AUTH={auth} needs {prefix}_TOKEN")
        if auth == "basic" and not (connection.username and connection.password):
            raise ValueError(f"{prefix}_AUTH=basic needs {prefix}_USERNAME and {prefix}_PASSWORD")
        return connection


class BankHttp:
    """GET requests to one of the bank's systems.

    A 404 raises NotFound. A connection failure, a timeout or a 5xx is retried `retries` times,
    then raises BankUnavailable, as does any other error status or a body that is not JSON.
    Only reads are made, so a retry cannot repeat a change.
    """

    def __init__(
        self,
        connection: Connection,
        *,
        retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.connection = connection
        self.retries = retries
        headers, auth = _auth(connection)
        self._http = httpx.AsyncClient(
            base_url=connection.base_url.rstrip("/"),
            headers=headers,
            auth=auth,
            timeout=connection.timeout_s,
            verify=_tls(connection),
            transport=transport,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        query = {k: v for k, v in (params or {}).items() if v is not None}
        for attempt in range(self.retries + 1):
            last = attempt == self.retries
            try:
                response = await self._http.get(path, params=query)
            except httpx.TransportError as exc:  # connection refused, timeout, TLS failure...
                if last:
                    raise BankUnavailable(f"GET {path}: {type(exc).__name__}") from exc
                continue
            if response.status_code == 404:
                raise NotFound(path)
            if response.status_code >= 500 and not last:
                continue
            if response.status_code >= 400:
                raise BankUnavailable(f"GET {path}: HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError as exc:
                raise BankUnavailable(f"GET {path}: the response is not JSON") from exc
        raise AssertionError("unreachable")  # every attempt returns, raises or continues


def segment(value: str) -> str:
    """A value placed in a URL path, escaped so it stays one segment ("../x" cannot climb)."""
    return quote(value, safe="")


def mapped[T](convert: Callable[[Any], T], raw: Any, what: str) -> T:
    """Converts a response with a mapping function. A response missing a field, or with a
    field of the wrong kind, means the bank's interface is not what the client expects, so it
    raises BankUnavailable. (A bare KeyError would be reported as "not found".)"""
    try:
        return convert(raw)
    except (KeyError, IndexError, TypeError, ValueError, InvalidOperation) as exc:
        raise BankUnavailable(f"unexpected {what} from the bank: {exc!r}") from exc


def money(value: Any) -> str:
    """A decimal string with two places, from a number or a string."""
    return f"{Decimal(str(value).replace(',', '')):.2f}"


def iso_date(value: Any) -> str:
    """YYYY-MM-DD from a date or a timestamp."""
    return date.fromisoformat(str(value)[:10]).isoformat()


def optional(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _auth(connection: Connection) -> tuple[dict[str, str], httpx.Auth | None]:
    if connection.auth == "bearer":
        return {"Authorization": f"Bearer {connection.token}"}, None
    if connection.auth == "api_key":
        return {connection.api_key_header: connection.token}, None
    if connection.auth == "basic":
        return {}, httpx.BasicAuth(connection.username, connection.password)
    return {}, None


def _tls(connection: Connection) -> ssl.SSLContext | bool:
    if not (connection.ca_bundle or connection.client_cert):
        return True
    context = ssl.create_default_context(cafile=connection.ca_bundle or None)
    if connection.client_cert:
        context.load_cert_chain(connection.client_cert, connection.client_key or None)
    return context
