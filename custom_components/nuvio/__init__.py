"""Nuvio integration setup and actions."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .account import NuvioAccountApi, NuvioAuthError
from .api import NuvioApi
from .const import (
    ATTR_BACKDROP,
    ATTR_CONTENT_ID,
    ATTR_EPISODE,
    ATTR_EPISODE_TITLE,
    ATTR_LOGO,
    ATTR_MEDIA_TYPE,
    ATTR_POSTER,
    ATTR_SEASON,
    ATTR_TITLE,
    ATTR_VIDEO_ID,
    CONF_ACCESS_TOKEN,
    CONF_MANIFEST_URLS,
    CONF_PACKAGE_NAME,
    CONF_PROFILE_ID,
    CONF_REFRESH_TOKEN,
    DATA_ACCOUNT_API,
    DATA_API,
    DEFAULT_PACKAGE_NAME,
    DOMAIN,
    SERVICE_OPEN,
    SERVICE_PLAY,
)
from .launcher import deep_link, stream_intent_command, webos_launch_payload
from .frontend import async_register_frontend

type NuvioConfigEntry = ConfigEntry[dict[str, Any]]

BASE_SCHEMA = {
    probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
    probatio.Required(ATTR_MEDIA_TYPE): probatio.In(["movie", "series"]),
    probatio.Required(ATTR_CONTENT_ID): cv.string,
}

OPEN_SCHEMA = probatio.Schema(BASE_SCHEMA)
PLAY_SCHEMA = probatio.Schema(
    {
        **BASE_SCHEMA,
        probatio.Required(ATTR_TITLE): cv.string,
        probatio.Optional(ATTR_VIDEO_ID): cv.string,
        probatio.Optional(ATTR_POSTER): cv.url,
        probatio.Optional(ATTR_BACKDROP): cv.url,
        probatio.Optional(ATTR_LOGO): cv.url,
        probatio.Optional(ATTR_SEASON): probatio.Coerce(int),
        probatio.Optional(ATTR_EPISODE): probatio.Coerce(int),
        probatio.Optional(ATTR_EPISODE_TITLE): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: NuvioConfigEntry) -> bool:
    """Set up Nuvio from a config entry."""
    session = async_get_clientsession(hass)
    manifest_urls = list(entry.data[CONF_MANIFEST_URLS])
    account_api: NuvioAccountApi | None = None

    async def token_updated(token_data: dict[str, Any]) -> None:
        """Persist rotated Nuvio tokens."""
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_ACCESS_TOKEN: token_data[CONF_ACCESS_TOKEN],
                CONF_REFRESH_TOKEN: token_data.get(CONF_REFRESH_TOKEN)
                or entry.data[CONF_REFRESH_TOKEN],
            },
        )

    if refresh_token := entry.data.get(CONF_REFRESH_TOKEN):
        account_api = NuvioAccountApi(
            session,
            access_token=entry.data.get(CONF_ACCESS_TOKEN),
            refresh_token=refresh_token,
            token_updated=token_updated,
        )
        try:
            account_manifest_urls = await account_api.async_addon_urls(
                int(entry.data.get(CONF_PROFILE_ID, 1))
            )
        except NuvioAuthError:
            account_manifest_urls = []
        manifest_urls = list(dict.fromkeys([*account_manifest_urls, *manifest_urls]))

    entry.runtime_data = {
        DATA_API: NuvioApi(session, manifest_urls),
        DATA_ACCOUNT_API: account_api,
    }

    await async_register_frontend(hass)

    if not hass.services.has_service(DOMAIN, SERVICE_OPEN):

        async def handle_open(call: ServiceCall) -> None:
            entity_ids = call.data[ATTR_ENTITY_ID]
            registry = async_get_entity_registry(hass)
            webos_ids: list[str] = []
            generic_ids: list[str] = []
            for entity_id in entity_ids:
                registry_entry = registry.async_get(entity_id)
                if registry_entry is not None and registry_entry.platform == "webostv":
                    webos_ids.append(entity_id)
                else:
                    generic_ids.append(entity_id)

            if generic_ids:
                uri = deep_link(call.data[ATTR_MEDIA_TYPE], call.data[ATTR_CONTENT_ID])
                await hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        ATTR_ENTITY_ID: generic_ids,
                        "media_content_id": uri,
                        "media_content_type": "url",
                    },
                    blocking=True,
                )

            if webos_ids:
                payload = webos_launch_payload(
                    media_type=call.data[ATTR_MEDIA_TYPE],
                    content_id=call.data[ATTR_CONTENT_ID],
                    launch_mode="details",
                )
                await hass.services.async_call(
                    "webostv",
                    "command",
                    {
                        ATTR_ENTITY_ID: webos_ids,
                        "command": "system.launcher/launch",
                        "payload": payload,
                    },
                    blocking=True,
                )

        async def handle_play(call: ServiceCall) -> None:
            entity_ids = call.data[ATTR_ENTITY_ID]
            registry = async_get_entity_registry(hass)
            android_ids: list[str] = []
            webos_ids: list[str] = []
            invalid: list[str] = []

            for entity_id in entity_ids:
                registry_entry = registry.async_get(entity_id)
                if registry_entry is None:
                    invalid.append(entity_id)
                elif registry_entry.platform == "androidtv":
                    android_ids.append(entity_id)
                elif registry_entry.platform == "webostv":
                    webos_ids.append(entity_id)
                else:
                    invalid.append(entity_id)

            if invalid:
                raise HomeAssistantError(
                    "Nuvio playback supports ADB-based Android TV and LG webOS "
                    f"media_player entities: {', '.join(invalid)}"
                )

            if android_ids:
                loaded_entry = hass.config_entries.async_loaded_entries(DOMAIN)[0]
                command = stream_intent_command(
                    package_name=loaded_entry.data.get(
                        CONF_PACKAGE_NAME, DEFAULT_PACKAGE_NAME
                    ),
                    media_type=call.data[ATTR_MEDIA_TYPE],
                    content_id=call.data[ATTR_CONTENT_ID],
                    title=call.data[ATTR_TITLE],
                    video_id=call.data.get(ATTR_VIDEO_ID),
                    poster=call.data.get(ATTR_POSTER),
                    backdrop=call.data.get(ATTR_BACKDROP),
                    logo=call.data.get(ATTR_LOGO),
                    season=call.data.get(ATTR_SEASON),
                    episode=call.data.get(ATTR_EPISODE),
                    episode_title=call.data.get(ATTR_EPISODE_TITLE),
                )
                await hass.services.async_call(
                    "androidtv",
                    "adb_command",
                    {ATTR_ENTITY_ID: android_ids, "command": command},
                    blocking=True,
                )

            if webos_ids:
                payload = webos_launch_payload(
                    media_type=call.data[ATTR_MEDIA_TYPE],
                    content_id=call.data[ATTR_CONTENT_ID],
                    title=call.data[ATTR_TITLE],
                    video_id=call.data.get(ATTR_VIDEO_ID),
                    poster=call.data.get(ATTR_POSTER),
                    backdrop=call.data.get(ATTR_BACKDROP),
                    logo=call.data.get(ATTR_LOGO),
                    season=call.data.get(ATTR_SEASON),
                    episode=call.data.get(ATTR_EPISODE),
                    episode_title=call.data.get(ATTR_EPISODE_TITLE),
                    launch_mode="stream",
                )
                await hass.services.async_call(
                    "webostv",
                    "command",
                    {
                        ATTR_ENTITY_ID: webos_ids,
                        "command": "system.launcher/launch",
                        "payload": payload,
                    },
                    blocking=True,
                )

        hass.services.async_register(
            DOMAIN, SERVICE_OPEN, handle_open, schema=OPEN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PLAY, handle_play, schema=PLAY_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NuvioConfigEntry) -> bool:
    """Unload Nuvio."""
    if len(hass.config_entries.async_loaded_entries(DOMAIN)) <= 1:
        hass.services.async_remove(DOMAIN, SERVICE_OPEN)
        hass.services.async_remove(DOMAIN, SERVICE_PLAY)
    return True
