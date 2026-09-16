"""Config flow for Nuvio."""

from __future__ import annotations

import asyncio
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .account import NuvioAccountApi, NuvioAuthError
from .api import NuvioApi, NuvioApiError, normalize_manifest_url
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CONNECT_ACCOUNT,
    CONF_EMAIL,
    CONF_MANIFEST_URLS,
    CONF_PACKAGE_NAME,
    CONF_PROFILE_ID,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    DEFAULT_MANIFEST_URL,
    DEFAULT_PACKAGE_NAME,
    DEFAULT_PROFILE_ID,
    DOMAIN,
)


def _parse_urls(value: str) -> list[str]:
    """Turn newline/comma separated URLs into normalized URLs."""
    raw = value.replace(",", "\n").splitlines()
    urls = [normalize_manifest_url(url) for url in raw if url.strip()]
    if not urls:
        raise ValueError("At least one URL is required")
    return list(dict.fromkeys(urls))


class NuvioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Nuvio config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._pending_data: dict[str, Any] = {}
        self._account_api: NuvioAccountApi | None = None
        self._login: dict[str, Any] | None = None
        self._login_task: asyncio.Task[dict[str, Any]] | None = None
        self._reconfigure = False

    async def _async_start_account_login(self) -> ConfigFlowResult:
        """Start Nuvio's device authorization flow."""
        self._account_api = NuvioAccountApi(async_get_clientsession(self.hass))
        self._login = await self._account_api.async_start_device_login()
        self._login_task = self.hass.async_create_task(
            self._account_api.async_wait_for_device_login(self._login)
        )
        return await self.async_step_device()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure Nuvio."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                urls = _parse_urls(user_input[CONF_MANIFEST_URLS])
                api = NuvioApi(async_get_clientsession(self.hass), urls)
                await api.async_addons()
            except ValueError:
                errors[CONF_MANIFEST_URLS] = "invalid_url"
            except NuvioApiError:
                errors[CONF_MANIFEST_URLS] = "cannot_connect"
            else:
                self._pending_data = {
                    CONF_MANIFEST_URLS: urls,
                    CONF_PACKAGE_NAME: user_input[CONF_PACKAGE_NAME].strip(),
                    CONF_PROFILE_ID: user_input[CONF_PROFILE_ID],
                }
                if not user_input[CONF_CONNECT_ACCOUNT]:
                    return self.async_create_entry(
                        title="Nuvio", data=self._pending_data
                    )
                try:
                    return await self._async_start_account_login()
                except NuvioAuthError:
                    errors["base"] = "login_start_failed"

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_MANIFEST_URLS,
                    default=(user_input or {}).get(
                        CONF_MANIFEST_URLS, DEFAULT_MANIFEST_URL
                    ),
                ): str,
                probatio.Required(
                    CONF_PACKAGE_NAME,
                    default=(user_input or {}).get(
                        CONF_PACKAGE_NAME, DEFAULT_PACKAGE_NAME
                    ),
                ): str,
                probatio.Required(
                    CONF_PROFILE_ID,
                    default=(user_input or {}).get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID),
                ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=5)),
                probatio.Required(
                    CONF_CONNECT_ACCOUNT,
                    default=(user_input or {}).get(CONF_CONNECT_ACCOUNT, True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect, reconnect, or disconnect an account on an existing entry."""
        self._reconfigure = True
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pending_data = {
                **entry.data,
                CONF_PROFILE_ID: user_input[CONF_PROFILE_ID],
            }
            if not user_input[CONF_CONNECT_ACCOUNT]:
                for key in (
                    CONF_ACCESS_TOKEN,
                    CONF_REFRESH_TOKEN,
                    CONF_USER_ID,
                    CONF_EMAIL,
                ):
                    self._pending_data.pop(key, None)
                return self.async_update_reload_and_abort(
                    entry, data=self._pending_data, title="Nuvio"
                )
            try:
                return await self._async_start_account_login()
            except NuvioAuthError:
                errors["base"] = "login_start_failed"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_PROFILE_ID,
                        default=(user_input or {}).get(
                            CONF_PROFILE_ID,
                            entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID),
                        ),
                    ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=5)),
                    probatio.Required(
                        CONF_CONNECT_ACCOUNT,
                        default=(user_input or {}).get(CONF_CONNECT_ACCOUNT, True),
                    ): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Wait for Nuvio device authorization."""
        assert self._login is not None
        assert self._login_task is not None
        if self._login_task.done():
            if self._login_task.exception():
                return self.async_show_progress_done(next_step_id="login_failed")
            return self.async_show_progress_done(next_step_id="finish")
        return self.async_show_progress(
            step_id="device",
            progress_action="wait_for_device",
            progress_task=self._login_task,
            description_placeholders={
                "url": str(self._login["verification_uri_complete"]),
                "code": str(self._login["user_code"]),
            },
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Store the authorized renewable session."""
        assert self._login_task is not None
        token_data = self._login_task.result()
        user = token_data.get("user") or {}
        self._pending_data.update(
            {
                CONF_ACCESS_TOKEN: token_data["access_token"],
                CONF_REFRESH_TOKEN: token_data["refresh_token"],
                CONF_USER_ID: user.get("id"),
                CONF_EMAIL: user.get("email"),
            }
        )
        title = f"Nuvio · {user.get('email')}" if user.get("email") else "Nuvio"
        if self._reconfigure:
            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(),
                data=self._pending_data,
                title=title,
            )
        return self.async_create_entry(title=title, data=self._pending_data)

    async def async_step_login_failed(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Report a failed or expired device login."""
        return self.async_abort(reason="login_failed")
