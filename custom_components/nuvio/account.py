"""Nuvio account authentication and sync API client."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from aiohttp import ClientError, ClientSession

from .const import NUVIO_API_KEY, NUVIO_BACKEND_URL


class NuvioAuthError(Exception):
    """Raised when Nuvio authentication or account sync fails."""


class NuvioLoginExpired(NuvioAuthError):
    """Raised when a device login expires before approval."""


class NuvioAccountApi:
    """Use Nuvio's public device-login and account synchronization API."""

    def __init__(
        self,
        session: ClientSession,
        *,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_updated: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._session = session
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._token_updated = token_updated

    def _headers(self, *, authenticated: bool = False) -> dict[str, str]:
        headers = {
            "apikey": NUVIO_API_KEY,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        token = self.access_token if authenticated else NUVIO_API_KEY
        headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        authenticated: bool = False,
        retry_auth: bool = True,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{NUVIO_BACKEND_URL}{path}",
                headers=self._headers(authenticated=authenticated),
                json=json,
                timeout=30,
            ) as response:
                if response.status == 401 and authenticated and retry_auth:
                    await self.async_refresh()
                    return await self._request(
                        method,
                        path,
                        json=json,
                        authenticated=True,
                        retry_auth=False,
                    )
                if response.status >= 400:
                    body = await response.text()
                    raise NuvioAuthError(
                        f"Nuvio returned HTTP {response.status}: {body[:200]}"
                    )
                if response.status == 204:
                    return None
                return await response.json(content_type=None)
        except (ClientError, TimeoutError, ValueError) as err:
            raise NuvioAuthError(f"Could not contact Nuvio: {err}") from err

    async def async_start_device_login(self) -> dict[str, Any]:
        """Create a device authorization request."""
        nonce = secrets.token_urlsafe(24)
        result = await self._request(
            "POST",
            "/rest/v1/rpc/start_device_login_session",
            json={
                "p_device_nonce": nonce,
                "p_redirect_base_url": "https://nuvio.tv/link",
                "p_device_type": "tv",
                "p_device_name": "Home Assistant",
            },
        )
        if not isinstance(result, list) or not result:
            raise NuvioAuthError("Nuvio returned no device login session")
        login = dict(result[0])
        login["device_nonce"] = nonce
        return login

    async def async_wait_for_device_login(
        self, login: dict[str, Any]
    ) -> dict[str, Any]:
        """Poll a device authorization and exchange it for a renewable session."""
        interval = max(2, int(login.get("poll_interval_seconds", 3)))
        expires_at = datetime.fromisoformat(
            str(login["expires_at"]).replace("Z", "+00:00")
        )
        while datetime.now(UTC) < expires_at:
            await asyncio.sleep(interval)
            result = await self.async_poll_device_login(login)
            status = str(result.get("status", "")).lower()
            interval = max(2, int(result.get("poll_interval_seconds") or interval))
            if status == "approved":
                return await self.async_exchange_device_login(login)
            if status in {"expired", "used", "cancelled"}:
                raise NuvioLoginExpired(f"Nuvio device login is {status}")
        raise NuvioLoginExpired("Nuvio device login expired")

    async def async_poll_device_login(self, login: dict[str, Any]) -> dict[str, Any]:
        """Check the current state of a device authorization request once."""
        result = await self._request(
            "POST",
            "/rest/v1/rpc/poll_tv_login_session",
            json={
                "p_code": login["device_code"],
                "p_device_nonce": login["device_nonce"],
            },
        )
        if not isinstance(result, list) or not result:
            raise NuvioAuthError("Nuvio returned no login status")
        return result[0]

    async def async_exchange_device_login(
        self, login: dict[str, Any]
    ) -> dict[str, Any]:
        """Exchange an approved device login for access and refresh tokens."""
        token_data = await self._request(
            "POST",
            "/functions/v1/tv-logins-exchange",
            json={
                "code": login["device_code"],
                "device_nonce": login["device_nonce"],
            },
        )
        if not isinstance(token_data, dict):
            raise NuvioAuthError("Nuvio returned an invalid token response")
        self.access_token = str(token_data.get("access_token", ""))
        self.refresh_token = str(token_data.get("refresh_token", ""))
        if not self.access_token or not self.refresh_token:
            raise NuvioAuthError("Nuvio returned an incomplete token response")
        return token_data

    async def async_refresh(self) -> dict[str, Any]:
        """Refresh the Nuvio session and persist the rotated refresh token."""
        if not self.refresh_token:
            raise NuvioAuthError("Nuvio account needs to be reauthenticated")
        token_data = await self._request(
            "POST",
            "/auth/v1/token?grant_type=refresh_token",
            json={"refresh_token": self.refresh_token},
        )
        if not isinstance(token_data, dict):
            raise NuvioAuthError("Nuvio returned an invalid refresh response")
        self.access_token = str(token_data.get("access_token", ""))
        self.refresh_token = str(token_data.get("refresh_token") or self.refresh_token)
        if self._token_updated is not None:
            await self._token_updated(token_data)
        return token_data

    async def async_profiles(self) -> list[dict[str, Any]]:
        """Return profiles belonging to the signed-in account."""
        data = await self._request(
            "POST",
            "/rest/v1/rpc/sync_pull_profiles",
            json={},
            authenticated=True,
        )
        return [item for item in data or [] if isinstance(item, dict)]

    async def async_addon_urls(self, profile_id: int) -> list[str]:
        """Return enabled account addon manifests for a profile."""
        query = urlencode(
            {
                "select": "url,enabled,sort_order,profile_id",
                "profile_id": f"eq.{profile_id}",
                "enabled": "eq.true",
                "order": "sort_order.asc",
            }
        )
        data = await self._request(
            "GET", f"/rest/v1/addons?{query}", authenticated=True
        )
        return [
            str(item["url"])
            for item in data or []
            if isinstance(item, dict) and item.get("url")
        ]

    async def async_library(self, profile_id: int) -> list[dict[str, Any]]:
        """Return all saved library items for a profile."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = await self._request(
                "POST",
                "/rest/v1/rpc/sync_pull_library",
                json={"p_profile_id": profile_id, "p_limit": 200, "p_offset": offset},
                authenticated=True,
            )
            page = [item for item in page or [] if isinstance(item, dict)]
            items.extend(page)
            if len(page) < 200:
                return items
            offset += len(page)

    async def async_watch_progress(self, profile_id: int) -> list[dict[str, Any]]:
        """Return current watch-progress records for a profile."""
        data = await self._request(
            "POST",
            "/rest/v1/rpc/sync_pull_watch_progress",
            json={"p_profile_id": profile_id, "p_limit": 100},
            authenticated=True,
        )
        return [item for item in data or [] if isinstance(item, dict)]
