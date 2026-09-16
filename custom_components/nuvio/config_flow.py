"""Config flow for Nuvio."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NuvioApi, NuvioApiError, normalize_manifest_url
from .const import (
    CONF_MANIFEST_URLS,
    CONF_PACKAGE_NAME,
    DEFAULT_MANIFEST_URL,
    DEFAULT_PACKAGE_NAME,
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
                return self.async_create_entry(
                    title="Nuvio",
                    data={
                        CONF_MANIFEST_URLS: urls,
                        CONF_PACKAGE_NAME: user_input[CONF_PACKAGE_NAME].strip(),
                    },
                )

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
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
