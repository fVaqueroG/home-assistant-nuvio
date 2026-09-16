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
from homeassistant.helpers.typing import ConfigType

from .account import NuvioAccountApi, NuvioAuthError
from .api import NuvioApi
from .const import (
    ATTR_BACKDROP,
    ATTR_VIDEO_SIZE,
    ATTR_STREAM_DESCRIPTION,
    ATTR_IN_NUVIO,
    ATTR_INFO_HASH,
    ATTR_FILENAME,
    ATTR_FILE_IDX,
    ATTR_CONTENT_LANGUAGE,
    ATTR_ADDON_NAME,
    ATTR_ADDON_LOGO,
    ATTR_CONTENT_ID,
    ATTR_EPISODE,
    ATTR_EPISODE_TITLE,
    ATTR_LOGO,
    ATTR_MIME_TYPE,
    ATTR_KEY,
    ATTR_MEDIA_TYPE,
    ATTR_POSTER,
    ATTR_SEASON,
    ATTR_STREAM_TITLE,
    ATTR_STREAM_URL,
    ATTR_TITLE,
    ATTR_VIDEO_ID,
    CONF_ACCESS_TOKEN,
    CONF_DEBRID_API_KEY,
    CONF_DEBRID_PROVIDER,
    CONF_MANIFEST_URLS,
    CONF_PACKAGE_NAME,
    CONF_PROFILE_ID,
    CONF_REFRESH_TOKEN,
    DATA_ACCOUNT_API,
    DATA_API,
    DATA_DEBRID_RESOLVER,
    DEFAULT_PACKAGE_NAME,
    DOMAIN,
    SERVICE_OPEN,
    SERVICE_PLAY,
    SERVICE_PLAY_SOURCE,
    SERVICE_REMOTE_KEY,
)
from .launcher import (
    deep_link,
    direct_stream_command,
    player_intent_command,
    stream_intent_command,
    webos_launch_payload,
)
from .frontend import async_register_frontend
from .debrid import DebridResolver

type NuvioConfigEntry = ConfigEntry[dict[str, Any]]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Nuvio frontend resources before config entries do network I/O."""
    await async_register_frontend(hass)
    return True


BASE_SCHEMA = {
    probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
    probatio.Required(ATTR_MEDIA_TYPE): probatio.In(["movie", "series"]),
    probatio.Required(ATTR_CONTENT_ID): cv.string,
}

OPEN_SCHEMA = probatio.Schema(BASE_SCHEMA)
PLAY_SOURCE_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
        probatio.Required(ATTR_STREAM_URL): cv.url,
        probatio.Optional(ATTR_STREAM_TITLE): cv.string,
        probatio.Optional(ATTR_MIME_TYPE): cv.string,
        probatio.Optional(ATTR_IN_NUVIO, default=False): cv.boolean,
        probatio.Optional(ATTR_MEDIA_TYPE): probatio.In(["movie", "series"]),
        probatio.Optional(ATTR_CONTENT_ID): cv.string,
        probatio.Optional(ATTR_VIDEO_ID): cv.string,
        probatio.Optional(ATTR_TITLE): cv.string,
        probatio.Optional(ATTR_POSTER): cv.url,
        probatio.Optional(ATTR_BACKDROP): cv.url,
        probatio.Optional(ATTR_LOGO): cv.url,
        probatio.Optional(ATTR_SEASON): probatio.Coerce(int),
        probatio.Optional(ATTR_EPISODE): probatio.Coerce(int),
        probatio.Optional(ATTR_EPISODE_TITLE): cv.string,
        probatio.Optional(ATTR_FILENAME): cv.string,
        probatio.Optional(ATTR_VIDEO_SIZE): probatio.Coerce(int),
        probatio.Optional(ATTR_ADDON_NAME): cv.string,
        probatio.Optional(ATTR_ADDON_LOGO): cv.url,
        probatio.Optional(ATTR_STREAM_DESCRIPTION): cv.string,
        probatio.Optional(ATTR_INFO_HASH): cv.string,
        probatio.Optional(ATTR_FILE_IDX): probatio.Coerce(int),
        probatio.Optional(ATTR_CONTENT_LANGUAGE): cv.string,
    }
)

REMOTE_KEY_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
        probatio.Required(ATTR_KEY): probatio.In(
            ["up", "down", "left", "right", "ok", "back", "home", "wake"]
        ),
    }
)

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
    await async_register_frontend(hass)
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

    synced_debrid_credentials: dict[str, str] = {}
    if refresh_token := entry.data.get(CONF_REFRESH_TOKEN):
        account_api = NuvioAccountApi(
            session,
            access_token=entry.data.get(CONF_ACCESS_TOKEN),
            refresh_token=refresh_token,
            token_updated=token_updated,
        )
        profile_id = int(entry.data.get(CONF_PROFILE_ID, 1))
        try:
            account_manifest_urls = await account_api.async_addon_urls(profile_id)
        except NuvioAuthError:
            account_manifest_urls = []
        try:
            synced_debrid_credentials = await account_api.async_provider_credentials(
                profile_id
            )
        except NuvioAuthError:
            synced_debrid_credentials = {}
        manifest_urls = list(dict.fromkeys([*account_manifest_urls, *manifest_urls]))

    entry.runtime_data = {
        DATA_API: NuvioApi(session, manifest_urls),
        DATA_ACCOUNT_API: account_api,
        DATA_DEBRID_RESOLVER: DebridResolver(
            session,
            provider=entry.data.get(CONF_DEBRID_PROVIDER),
            api_key=entry.data.get(CONF_DEBRID_API_KEY),
            credentials=synced_debrid_credentials,
        ),
    }

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
            android_remote_ids: list[str] = []
            webos_ids: list[str] = []
            invalid: list[str] = []

            for entity_id in entity_ids:
                registry_entry = registry.async_get(entity_id)
                if registry_entry is None:
                    invalid.append(entity_id)
                elif registry_entry.platform == "androidtv":
                    android_ids.append(entity_id)
                elif registry_entry.platform == "androidtv_remote":
                    android_remote_ids.append(entity_id)
                elif registry_entry.platform == "webostv":
                    webos_ids.append(entity_id)
                else:
                    invalid.append(entity_id)

            if invalid:
                raise HomeAssistantError(
                    "Nuvio playback supports ADB-based Android TV, Android TV Remote, and LG webOS "
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

            if android_remote_ids:
                # Android TV Remote can launch app/deep links, but it cannot send
                # the arbitrary Android intent extras used by Nuvio's direct
                # stream contract. Fall back to opening the selected title.
                uri = deep_link(call.data[ATTR_MEDIA_TYPE], call.data[ATTR_CONTENT_ID])
                await hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        ATTR_ENTITY_ID: android_remote_ids,
                        "media_content_id": uri,
                        "media_content_type": "url",
                    },
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

        async def handle_play_source(call: ServiceCall) -> None:
            """Play one exact HTTP/HLS stream source on the selected device."""
            entity_ids = call.data[ATTR_ENTITY_ID]
            stream_url = str(call.data[ATTR_STREAM_URL])
            title = call.data.get(ATTR_STREAM_TITLE)
            mime_type = call.data.get(ATTR_MIME_TYPE)
            registry = async_get_entity_registry(hass)

            android_ids: list[str] = []
            android_remote_ids: list[str] = []
            webos_ids: list[str] = []
            invalid: list[str] = []

            for entity_id in entity_ids:
                registry_entry = registry.async_get(entity_id)
                if registry_entry is None:
                    invalid.append(entity_id)
                elif registry_entry.platform == "androidtv":
                    android_ids.append(entity_id)
                elif registry_entry.platform == "androidtv_remote":
                    android_remote_ids.append(entity_id)
                elif registry_entry.platform == "webostv":
                    webos_ids.append(entity_id)
                else:
                    invalid.append(entity_id)

            if invalid:
                raise HomeAssistantError(
                    "Direct source playback supports Android TV, Android TV Remote, "
                    f"and LG webOS media players: {', '.join(invalid)}"
                )

            if call.data.get(ATTR_IN_NUVIO):
                loaded_entry = hass.config_entries.async_loaded_entries(DOMAIN)[0]
                profile_id = int(loaded_entry.data.get(CONF_PROFILE_ID, 1))
                source_title = (
                    call.data.get(ATTR_STREAM_TITLE)
                    or call.data.get(ATTR_TITLE)
                    or "Nuvio"
                )

                if android_ids:
                    command = player_intent_command(
                        package_name=loaded_entry.data.get(
                            CONF_PACKAGE_NAME, DEFAULT_PACKAGE_NAME
                        ),
                        stream_url=stream_url,
                        stream_title=source_title,
                        media_type=call.data.get(ATTR_MEDIA_TYPE),
                        content_id=call.data.get(ATTR_CONTENT_ID),
                        video_id=call.data.get(ATTR_VIDEO_ID),
                        title=call.data.get(ATTR_TITLE),
                        poster=call.data.get(ATTR_POSTER),
                        backdrop=call.data.get(ATTR_BACKDROP),
                        logo=call.data.get(ATTR_LOGO),
                        season=call.data.get(ATTR_SEASON),
                        episode=call.data.get(ATTR_EPISODE),
                        episode_title=call.data.get(ATTR_EPISODE_TITLE),
                        filename=call.data.get(ATTR_FILENAME),
                        video_size=call.data.get(ATTR_VIDEO_SIZE),
                        addon_name=call.data.get(ATTR_ADDON_NAME),
                        addon_logo=call.data.get(ATTR_ADDON_LOGO),
                        stream_description=call.data.get(ATTR_STREAM_DESCRIPTION),
                        info_hash=call.data.get(ATTR_INFO_HASH),
                        file_idx=call.data.get(ATTR_FILE_IDX),
                        content_language=call.data.get(ATTR_CONTENT_LANGUAGE),
                        profile_id=profile_id,
                    )
                    await hass.services.async_call(
                        "androidtv",
                        "adb_command",
                        {ATTR_ENTITY_ID: android_ids, "command": command},
                        blocking=True,
                    )

                if android_remote_ids:
                    # Android TV Remote cannot send arbitrary intent extras.
                    # Fall back to Nuvio's title/episode stream screen.
                    if (
                        call.data.get(ATTR_MEDIA_TYPE)
                        and call.data.get(ATTR_CONTENT_ID)
                    ):
                        uri = deep_link(
                            call.data[ATTR_MEDIA_TYPE],
                            call.data[ATTR_CONTENT_ID],
                        )
                        await hass.services.async_call(
                            "media_player",
                            "play_media",
                            {
                                ATTR_ENTITY_ID: android_remote_ids,
                                "media_content_id": uri,
                                "media_content_type": "url",
                            },
                            blocking=True,
                        )
                    else:
                        raise HomeAssistantError(
                            "Exact Nuvio internal-player launch on Android requires "
                            "the ADB-based Android TV entity."
                        )

                if webos_ids:
                    payload = webos_launch_payload(
                        media_type=call.data.get(ATTR_MEDIA_TYPE) or "movie",
                        content_id=call.data.get(ATTR_CONTENT_ID)
                        or call.data.get(ATTR_VIDEO_ID)
                        or "external",
                        title=call.data.get(ATTR_TITLE),
                        video_id=call.data.get(ATTR_VIDEO_ID),
                        poster=call.data.get(ATTR_POSTER),
                        backdrop=call.data.get(ATTR_BACKDROP),
                        logo=call.data.get(ATTR_LOGO),
                        season=call.data.get(ATTR_SEASON),
                        episode=call.data.get(ATTR_EPISODE),
                        episode_title=call.data.get(ATTR_EPISODE_TITLE),
                        launch_mode="player",
                        stream_url=stream_url,
                        stream_title=source_title,
                        filename=call.data.get(ATTR_FILENAME),
                        video_size=call.data.get(ATTR_VIDEO_SIZE),
                        addon_name=call.data.get(ATTR_ADDON_NAME),
                        addon_logo=call.data.get(ATTR_ADDON_LOGO),
                        stream_description=call.data.get(ATTR_STREAM_DESCRIPTION),
                        info_hash=call.data.get(ATTR_INFO_HASH),
                        file_idx=call.data.get(ATTR_FILE_IDX),
                        content_language=call.data.get(ATTR_CONTENT_LANGUAGE),
                        profile_id=profile_id,
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
                return

            if android_ids:
                command = direct_stream_command(
                    stream_url,
                    mime_type=mime_type or "video/*",
                )
                await hass.services.async_call(
                    "androidtv",
                    "adb_command",
                    {ATTR_ENTITY_ID: android_ids, "command": command},
                    blocking=True,
                )

            if android_remote_ids:
                await hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        ATTR_ENTITY_ID: android_remote_ids,
                        "media_content_id": stream_url,
                        "media_content_type": "url",
                    },
                    blocking=True,
                )

            if webos_ids:
                payload: dict[str, Any] = {"target": stream_url}
                if title:
                    payload["title"] = title
                if mime_type:
                    payload["mimeType"] = mime_type
                await hass.services.async_call(
                    "webostv",
                    "command",
                    {
                        ATTR_ENTITY_ID: webos_ids,
                        "command": "media.viewer/open",
                        "payload": payload,
                    },
                    blocking=True,
                )

        async def handle_remote_key(call: ServiceCall) -> None:
            """Send a navigation key to the selected TV."""
            entity_ids = call.data[ATTR_ENTITY_ID]
            key = call.data[ATTR_KEY]
            registry = async_get_entity_registry(hass)

            adb_keycodes = {
                "up": "KEYCODE_DPAD_UP",
                "down": "KEYCODE_DPAD_DOWN",
                "left": "KEYCODE_DPAD_LEFT",
                "right": "KEYCODE_DPAD_RIGHT",
                "ok": "KEYCODE_DPAD_CENTER",
                "back": "KEYCODE_BACK",
                "home": "KEYCODE_HOME",
                "wake": "KEYCODE_WAKEUP",
            }
            android_remote_commands = {
                "up": "DPAD_UP",
                "down": "DPAD_DOWN",
                "left": "DPAD_LEFT",
                "right": "DPAD_RIGHT",
                "ok": "DPAD_CENTER",
                "back": "BACK",
                "home": "HOME",
                # HOME reliably wakes/dismisses the screensaver without
                # risking a POWER toggle on an already-on television.
                "wake": "HOME",
            }
            webos_buttons = {
                "up": "UP",
                "down": "DOWN",
                "left": "LEFT",
                "right": "RIGHT",
                "ok": "ENTER",
                "back": "BACK",
                "home": "HOME",
                "wake": "HOME",
            }

            unsupported: list[str] = []
            for entity_id in entity_ids:
                registry_entry = registry.async_get(entity_id)
                if registry_entry is None:
                    unsupported.append(entity_id)
                    continue

                if registry_entry.platform == "androidtv":
                    command = (
                        "input keyevent KEYCODE_WAKEUP; input keyevent KEYCODE_HOME"
                        if key == "wake"
                        else f"input keyevent {adb_keycodes[key]}"
                    )
                    await hass.services.async_call(
                        "androidtv",
                        "adb_command",
                        {
                            ATTR_ENTITY_ID: [entity_id],
                            "command": command,
                        },
                        blocking=True,
                    )
                    continue

                if registry_entry.platform == "androidtv_remote":
                    remote_entity_id = next(
                        (
                            candidate.entity_id
                            for candidate in registry.entities.values()
                            if candidate.entity_id.startswith("remote.")
                            and candidate.platform == "androidtv_remote"
                            and candidate.config_entry_id == registry_entry.config_entry_id
                        ),
                        None,
                    )
                    if remote_entity_id is None:
                        unsupported.append(entity_id)
                        continue
                    await hass.services.async_call(
                        "remote",
                        "send_command",
                        {
                            ATTR_ENTITY_ID: [remote_entity_id],
                            "command": [android_remote_commands[key]],
                        },
                        blocking=True,
                    )
                    continue

                if registry_entry.platform == "webostv":
                    await hass.services.async_call(
                        "webostv",
                        "button",
                        {
                            ATTR_ENTITY_ID: [entity_id],
                            "button": webos_buttons[key],
                        },
                        blocking=True,
                    )
                    continue

                unsupported.append(entity_id)

            if unsupported:
                raise HomeAssistantError(
                    "Nuvio remote control supports Android TV (ADB), Android TV Remote, "
                    f"and LG webOS media players: {', '.join(unsupported)}"
                )

        hass.services.async_register(
            DOMAIN, SERVICE_OPEN, handle_open, schema=OPEN_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PLAY, handle_play, schema=PLAY_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PLAY_SOURCE, handle_play_source, schema=PLAY_SOURCE_SCHEMA
        )
        hass.services.async_register(
            DOMAIN, SERVICE_REMOTE_KEY, handle_remote_key, schema=REMOTE_KEY_SCHEMA
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NuvioConfigEntry) -> bool:
    """Unload Nuvio."""
    if len(hass.config_entries.async_loaded_entries(DOMAIN)) <= 1:
        hass.services.async_remove(DOMAIN, SERVICE_OPEN)
        hass.services.async_remove(DOMAIN, SERVICE_PLAY)
        hass.services.async_remove(DOMAIN, SERVICE_PLAY_SOURCE)
        hass.services.async_remove(DOMAIN, SERVICE_REMOTE_KEY)
    return True
