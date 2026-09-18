"""Config flow for Nuvio."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .account import NuvioAccountApi, NuvioAuthError, NuvioLoginExpired
from .api import NuvioApi, NuvioApiError, normalize_manifest_url
from .tmdb import TmdbApiError, TmdbWatchApi
from .tvdb import TvdbApi, TvdbApiError
from .justwatch import JustWatchAuthError, JustWatchGraphQLApi
from .providers import (
    normalize_provider_text,
    normalize_selected_provider,
    provider_catalog_options,
    provider_label,
    streaming_provider_key,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CONNECT_ACCOUNT,
    CONF_EMAIL,
    CONF_DEBRID_API_KEY,
    CONF_DEBRID_PROVIDER,
    CONF_MANIFEST_URLS,
    CONF_PACKAGE_NAME,
    CONF_PROFILE_ID,
    CONF_REFRESH_TOKEN,
    CONF_STREAMING_PROVIDERS,
    CONF_WATCHHUB_COUNTRY,
    CONF_TMDB_ACCESS_TOKEN,
    CONF_TVDB_API_KEY,
    CONF_TVDB_SUBSCRIBER_PIN,
    CONF_CONNECT_JUSTWATCH_ACCOUNT,
    CONF_JUSTWATCH_EMAIL,
    CONF_JUSTWATCH_PASSWORD,
    CONF_JUSTWATCH_ACCESS_TOKEN,
    CONF_JUSTWATCH_REFRESH_TOKEN,
    CONF_USER_ID,
    DEFAULT_MANIFEST_URL,
    DEFAULT_DEBRID_PROVIDER,
    DEFAULT_PACKAGE_NAME,
    DEFAULT_STREAMING_PROVIDERS,
    DEFAULT_WATCHHUB_COUNTRY,
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


DEBRID_OPTIONS = [
    selector.SelectOptionDict(value="none", label="None"),
    selector.SelectOptionDict(value="torbox", label="TorBox"),
    selector.SelectOptionDict(value="premiumize", label="Premiumize"),
    selector.SelectOptionDict(value="realdebrid", label="Real-Debrid"),
]

CONF_MANAGE_JUSTWATCH_ACCOUNT = "manage_justwatch_account"


def _streaming_provider_selector(
    extra: dict[str, str] | None = None,
) -> selector.SelectSelector:
    """Return a provider selector with built-ins plus synced/custom providers."""
    options = [
        selector.SelectOptionDict(value=key, label=label)
        for key, label in provider_catalog_options(extra)
    ]
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options,
            multiple=True,
            custom_value=True,
        )
    )


def _debrid_key_selector() -> selector.TextSelector:
    return selector.TextSelector(
        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
    )


class NuvioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a Nuvio config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._pending_data: dict[str, Any] = {}
        self._account_api: NuvioAccountApi | None = None
        self._login: dict[str, Any] | None = None
        self._reconfigure = False
        self._streaming_provider_options: dict[str, str] = {}
        self._connect_nuvio_after_justwatch = False

    async def _async_discover_streaming_providers(self, entry) -> None:
        """Add provider folders from the synced Nuvio Streaming collection."""
        discovered: dict[str, str] = {}
        stored_providers = entry.data.get(CONF_STREAMING_PROVIDERS, [])
        if isinstance(stored_providers, str):
            stored_providers = [stored_providers]
        for value in stored_providers:
            key = normalize_selected_provider(value)
            if key:
                discovered[key] = provider_label(key)

        refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
        if not refresh_token:
            self._streaming_provider_options = discovered
            return

        account_api = NuvioAccountApi(
            async_get_clientsession(self.hass),
            access_token=entry.data.get(CONF_ACCESS_TOKEN),
            refresh_token=refresh_token,
        )
        profile_id = int(entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID))
        try:
            collections = await account_api.async_collections(profile_id)
        except NuvioAuthError:
            self._streaming_provider_options = discovered
            return

        streaming_titles = {
            "streaming",
            "streaming services",
            "servicios de streaming",
            "plataformas de streaming",
        }
        for collection in collections:
            title = normalize_provider_text(collection.get("title"))
            if title not in streaming_titles:
                continue
            for folder in collection.get("folders") or []:
                if not isinstance(folder, dict):
                    continue
                label = str(folder.get("title") or "").strip()
                key = streaming_provider_key(label)
                if key and label:
                    discovered[key] = label

        self._streaming_provider_options = discovered

    async def _async_start_account_login(self) -> ConfigFlowResult:
        """Start Nuvio's device authorization flow."""
        self._account_api = NuvioAccountApi(async_get_clientsession(self.hass))
        self._login = await self._account_api.async_start_device_login()
        return await self.async_step_device()

    async def _async_finish_pending_configuration(self) -> ConfigFlowResult:
        """Finish setup after an optional JustWatch authentication step."""
        if self._reconfigure:
            entry = self._get_reconfigure_entry()
            if not self._connect_nuvio_after_justwatch:
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

            if entry.data.get(CONF_REFRESH_TOKEN):
                return self.async_update_reload_and_abort(
                    entry,
                    data=self._pending_data,
                    title=entry.title,
                )

            try:
                return await self._async_start_account_login()
            except NuvioAuthError:
                return self.async_abort(reason="login_failed")

        if not self._connect_nuvio_after_justwatch:
            return self.async_create_entry(title="Nuvio", data=self._pending_data)

        try:
            return await self._async_start_account_login()
        except NuvioAuthError:
            return self.async_abort(reason="login_failed")

    def _justwatch_session_present(self) -> bool:
        """Return whether pending config contains a usable JustWatch session."""
        return bool(
            self._pending_data.get(CONF_JUSTWATCH_REFRESH_TOKEN)
            or self._pending_data.get(CONF_JUSTWATCH_ACCESS_TOKEN)
        )

    async def async_step_justwatch(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to connect or manage the JustWatch account."""
        options = ["justwatch_email", "justwatch_token"]
        if self._reconfigure and self._justwatch_session_present():
            options.append("justwatch_disconnect")
        return self.async_show_menu(
            step_id="justwatch",
            menu_options=options,
        )

    async def async_step_justwatch_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect JustWatch with email/password and store only renewable tokens."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = str(user_input.get(CONF_JUSTWATCH_EMAIL, "") or "").strip()
            password = str(user_input.get(CONF_JUSTWATCH_PASSWORD, "") or "")
            try:
                api = JustWatchGraphQLApi(async_get_clientsession(self.hass))
                auth = await api.async_sign_in(email, password)
            except JustWatchAuthError:
                errors["base"] = "justwatch_credentials_invalid"
            else:
                self._pending_data.update(
                    {
                        CONF_CONNECT_JUSTWATCH_ACCOUNT: True,
                        CONF_JUSTWATCH_EMAIL: auth.get("email") or email,
                        CONF_JUSTWATCH_ACCESS_TOKEN: auth["access_token"],
                        CONF_JUSTWATCH_REFRESH_TOKEN: auth["refresh_token"],
                    }
                )
                return await self._async_finish_pending_configuration()

        return self.async_show_form(
            step_id="justwatch_email",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_JUSTWATCH_EMAIL,
                        default=str(
                            self._pending_data.get(CONF_JUSTWATCH_EMAIL, "") or ""
                        ),
                    ): str,
                    probatio.Required(CONF_JUSTWATCH_PASSWORD): _debrid_key_selector(),
                }
            ),
            errors=errors,
        )

    async def async_step_justwatch_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect a social-login JustWatch account with a browser access token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            browser_token = str(
                user_input.get(CONF_JUSTWATCH_ACCESS_TOKEN, "") or ""
            ).strip()
            try:
                api = JustWatchGraphQLApi(
                    async_get_clientsession(self.hass),
                    access_token=browser_token,
                )
                identity = await api.async_validate_auth()
            except JustWatchAuthError:
                errors["base"] = "justwatch_credentials_invalid"
            else:
                self._pending_data.pop(CONF_JUSTWATCH_REFRESH_TOKEN, None)
                self._pending_data.update(
                    {
                        CONF_CONNECT_JUSTWATCH_ACCOUNT: True,
                        CONF_JUSTWATCH_EMAIL: identity.get("email") or "",
                        CONF_JUSTWATCH_ACCESS_TOKEN: browser_token,
                    }
                )
                return await self._async_finish_pending_configuration()

        return self.async_show_form(
            step_id="justwatch_token",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_JUSTWATCH_ACCESS_TOKEN
                    ): _debrid_key_selector(),
                }
            ),
            errors=errors,
        )

    async def async_step_justwatch_disconnect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm disconnection of the JustWatch account."""
        if user_input is not None:
            for key in (
                CONF_CONNECT_JUSTWATCH_ACCOUNT,
                CONF_JUSTWATCH_EMAIL,
                CONF_JUSTWATCH_ACCESS_TOKEN,
                CONF_JUSTWATCH_REFRESH_TOKEN,
            ):
                self._pending_data.pop(key, None)
            return await self._async_finish_pending_configuration()

        return self.async_show_form(
            step_id="justwatch_disconnect",
            data_schema=probatio.Schema({}),
        )

    def _user_schema(self, user_input: dict[str, Any] | None = None) -> probatio.Schema:
        values = user_input or {}
        return probatio.Schema(
            {
                probatio.Required(
                    CONF_MANIFEST_URLS,
                    default=values.get(CONF_MANIFEST_URLS, DEFAULT_MANIFEST_URL),
                ): str,
                probatio.Required(
                    CONF_PACKAGE_NAME,
                    default=values.get(CONF_PACKAGE_NAME, DEFAULT_PACKAGE_NAME),
                ): str,
                probatio.Required(
                    CONF_PROFILE_ID,
                    default=values.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID),
                ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=5)),
                probatio.Required(
                    CONF_STREAMING_PROVIDERS,
                    default=values.get(
                        CONF_STREAMING_PROVIDERS, list(DEFAULT_STREAMING_PROVIDERS)
                    ),
                ): _streaming_provider_selector(self._streaming_provider_options),
                probatio.Required(
                    CONF_WATCHHUB_COUNTRY,
                    default=values.get(
                        CONF_WATCHHUB_COUNTRY,
                        str(
                            getattr(self.hass.config, "country", None)
                            or DEFAULT_WATCHHUB_COUNTRY
                        ).upper(),
                    ),
                ): selector.CountrySelector(),
                probatio.Required(
                    CONF_CONNECT_JUSTWATCH_ACCOUNT,
                    default=values.get(CONF_CONNECT_JUSTWATCH_ACCOUNT, False),
                ): bool,
                probatio.Optional(
                    CONF_TMDB_ACCESS_TOKEN,
                    default=values.get(CONF_TMDB_ACCESS_TOKEN, ""),
                ): _debrid_key_selector(),
                probatio.Optional(
                    CONF_TVDB_API_KEY,
                    default=values.get(CONF_TVDB_API_KEY, ""),
                ): _debrid_key_selector(),
                probatio.Optional(
                    CONF_TVDB_SUBSCRIBER_PIN,
                    default=values.get(CONF_TVDB_SUBSCRIBER_PIN, ""),
                ): _debrid_key_selector(),
                probatio.Required(
                    CONF_DEBRID_PROVIDER,
                    default=values.get(CONF_DEBRID_PROVIDER, DEFAULT_DEBRID_PROVIDER),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=DEBRID_OPTIONS)
                ),
                probatio.Optional(
                    CONF_DEBRID_API_KEY,
                    default=values.get(CONF_DEBRID_API_KEY, ""),
                ): _debrid_key_selector(),
                probatio.Required(
                    CONF_CONNECT_ACCOUNT,
                    default=values.get(CONF_CONNECT_ACCOUNT, True),
                ): bool,
            }
        )

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
                tmdb_token = str(
                    user_input.get(CONF_TMDB_ACCESS_TOKEN, "")
                ).strip()
                if tmdb_token:
                    try:
                        await TmdbWatchApi(
                            async_get_clientsession(self.hass), tmdb_token
                        ).async_validate()
                    except TmdbApiError:
                        errors[CONF_TMDB_ACCESS_TOKEN] = "tmdb_token_invalid"
                        return self.async_show_form(
                            step_id="user",
                            data_schema=self._user_schema(user_input),
                            errors=errors,
                        )

                tvdb_key = str(user_input.get(CONF_TVDB_API_KEY, "")).strip()
                tvdb_pin = str(
                    user_input.get(CONF_TVDB_SUBSCRIBER_PIN, "")
                ).strip()
                if tvdb_key:
                    try:
                        await TvdbApi(
                            async_get_clientsession(self.hass),
                            tvdb_key,
                            tvdb_pin,
                        ).async_validate()
                    except TvdbApiError:
                        errors[CONF_TVDB_API_KEY] = "tvdb_credentials_invalid"
                        return self.async_show_form(
                            step_id="user",
                            data_schema=self._user_schema(user_input),
                            errors=errors,
                        )

                provider = str(
                    user_input.get(CONF_DEBRID_PROVIDER, DEFAULT_DEBRID_PROVIDER)
                )
                api_key = str(user_input.get(CONF_DEBRID_API_KEY, "")).strip()
                if provider != "none" and not api_key:
                    errors[CONF_DEBRID_API_KEY] = "debrid_key_required"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=self._user_schema(user_input),
                        errors=errors,
                    )

                self._pending_data = {
                    CONF_MANIFEST_URLS: urls,
                    CONF_PACKAGE_NAME: user_input[CONF_PACKAGE_NAME].strip(),
                    CONF_PROFILE_ID: user_input[CONF_PROFILE_ID],
                    CONF_STREAMING_PROVIDERS: list(
                        dict.fromkeys(
                            key
                            for value in user_input.get(CONF_STREAMING_PROVIDERS, [])
                            if (key := normalize_selected_provider(value))
                        )
                    ),
                    CONF_WATCHHUB_COUNTRY: str(
                        user_input.get(
                            CONF_WATCHHUB_COUNTRY,
                            getattr(self.hass.config, "country", None)
                            or DEFAULT_WATCHHUB_COUNTRY,
                        )
                    ).upper(),
                    CONF_TMDB_ACCESS_TOKEN: tmdb_token,
                    CONF_TVDB_API_KEY: tvdb_key,
                    CONF_TVDB_SUBSCRIBER_PIN: tvdb_pin,
                    CONF_DEBRID_PROVIDER: provider,
                }
                if provider != "none":
                    self._pending_data[CONF_DEBRID_API_KEY] = api_key

                self._connect_nuvio_after_justwatch = bool(
                    user_input[CONF_CONNECT_ACCOUNT]
                )
                if user_input.get(CONF_CONNECT_JUSTWATCH_ACCOUNT, False):
                    return await self.async_step_justwatch()

                if not user_input[CONF_CONNECT_ACCOUNT]:
                    return self.async_create_entry(
                        title="Nuvio", data=self._pending_data
                    )
                try:
                    return await self._async_start_account_login()
                except NuvioAuthError:
                    errors["base"] = "login_start_failed"

        return self.async_show_form(
            step_id="user",
            data_schema=self._user_schema(user_input),
            errors=errors,
        )

    def _reconfigure_schema(
        self,
        entry,
        user_input: dict[str, Any] | None = None,
    ) -> probatio.Schema:
        values = user_input or {}

        def suggested(key: str, default: str = "") -> str:
            """Keep stored credentials visible/persistent in masked fields."""
            entered = str(values.get(key) or "").strip()
            if entered:
                return entered
            return str(entry.data.get(key, default) or "")

        selected_provider = str(
            values.get(
                CONF_DEBRID_PROVIDER,
                entry.data.get(CONF_DEBRID_PROVIDER, DEFAULT_DEBRID_PROVIDER),
            )
        )
        existing_provider = str(
            entry.data.get(CONF_DEBRID_PROVIDER, DEFAULT_DEBRID_PROVIDER)
        )
        debrid_suggested = (
            suggested(CONF_DEBRID_API_KEY)
            if selected_provider == existing_provider
            else ""
        )

        return probatio.Schema(
            {
                probatio.Required(
                    CONF_PACKAGE_NAME,
                    default=values.get(
                        CONF_PACKAGE_NAME,
                        entry.data.get(CONF_PACKAGE_NAME, DEFAULT_PACKAGE_NAME),
                    ),
                ): str,
                probatio.Required(
                    CONF_PROFILE_ID,
                    default=values.get(
                        CONF_PROFILE_ID,
                        entry.data.get(CONF_PROFILE_ID, DEFAULT_PROFILE_ID),
                    ),
                ): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=5)),
                probatio.Required(
                    CONF_STREAMING_PROVIDERS,
                    default=values.get(
                        CONF_STREAMING_PROVIDERS,
                        entry.data.get(
                            CONF_STREAMING_PROVIDERS,
                            list(DEFAULT_STREAMING_PROVIDERS),
                        ),
                    ),
                ): _streaming_provider_selector(self._streaming_provider_options),
                probatio.Required(
                    CONF_WATCHHUB_COUNTRY,
                    default=values.get(
                        CONF_WATCHHUB_COUNTRY,
                        entry.data.get(
                            CONF_WATCHHUB_COUNTRY,
                            str(
                                getattr(self.hass.config, "country", None)
                                or DEFAULT_WATCHHUB_COUNTRY
                            ).upper(),
                        ),
                    ),
                ): selector.CountrySelector(),
                probatio.Required(
                    CONF_MANAGE_JUSTWATCH_ACCOUNT,
                    default=values.get(CONF_MANAGE_JUSTWATCH_ACCOUNT, False),
                ): bool,
                probatio.Optional(
                    CONF_TMDB_ACCESS_TOKEN,
                    description={"suggested_value": suggested(CONF_TMDB_ACCESS_TOKEN)},
                ): _debrid_key_selector(),
                probatio.Optional(
                    CONF_TVDB_API_KEY,
                    description={"suggested_value": suggested(CONF_TVDB_API_KEY)},
                ): _debrid_key_selector(),
                probatio.Optional(
                    CONF_TVDB_SUBSCRIBER_PIN,
                    description={"suggested_value": suggested(CONF_TVDB_SUBSCRIBER_PIN)},
                ): _debrid_key_selector(),
                probatio.Required(
                    CONF_DEBRID_PROVIDER,
                    default=values.get(
                        CONF_DEBRID_PROVIDER,
                        entry.data.get(CONF_DEBRID_PROVIDER, DEFAULT_DEBRID_PROVIDER),
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=DEBRID_OPTIONS)
                ),
                probatio.Optional(
                    CONF_DEBRID_API_KEY,
                    description={"suggested_value": debrid_suggested},
                ): _debrid_key_selector(),
                probatio.Required(
                    CONF_CONNECT_ACCOUNT,
                    default=values.get(
                        CONF_CONNECT_ACCOUNT,
                        bool(entry.data.get(CONF_REFRESH_TOKEN)),
                    ),
                ): bool,
            }
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect, reconnect, or disconnect an account on an existing entry."""
        self._reconfigure = True
        entry = self._get_reconfigure_entry()
        if user_input is None:
            await self._async_discover_streaming_providers(entry)
        errors: dict[str, str] = {}
        if user_input is not None:
            entered_tmdb_token = str(
                user_input.get(CONF_TMDB_ACCESS_TOKEN, "")
            ).strip()
            existing_tmdb_token = str(
                entry.data.get(CONF_TMDB_ACCESS_TOKEN, "")
            ).strip()
            tmdb_token = entered_tmdb_token or existing_tmdb_token
            if entered_tmdb_token:
                try:
                    await TmdbWatchApi(
                        async_get_clientsession(self.hass), entered_tmdb_token
                    ).async_validate()
                except TmdbApiError:
                    errors[CONF_TMDB_ACCESS_TOKEN] = "tmdb_token_invalid"

            entered_tvdb_key = str(
                user_input.get(CONF_TVDB_API_KEY, "")
            ).strip()
            entered_tvdb_pin = str(
                user_input.get(CONF_TVDB_SUBSCRIBER_PIN, "")
            ).strip()
            existing_tvdb_key = str(
                entry.data.get(CONF_TVDB_API_KEY, "")
            ).strip()
            existing_tvdb_pin = str(
                entry.data.get(CONF_TVDB_SUBSCRIBER_PIN, "")
            ).strip()
            tvdb_key = entered_tvdb_key or existing_tvdb_key
            tvdb_pin = entered_tvdb_pin or existing_tvdb_pin
            if entered_tvdb_key or entered_tvdb_pin:
                if tvdb_key:
                    try:
                        await TvdbApi(
                            async_get_clientsession(self.hass),
                            tvdb_key,
                            tvdb_pin,
                        ).async_validate()
                    except TvdbApiError:
                        errors[CONF_TVDB_API_KEY] = "tvdb_credentials_invalid"

            provider = str(
                user_input.get(
                    CONF_DEBRID_PROVIDER,
                    entry.data.get(CONF_DEBRID_PROVIDER, DEFAULT_DEBRID_PROVIDER),
                )
            )
            entered_key = str(user_input.get(CONF_DEBRID_API_KEY, "")).strip()
            existing_provider = str(
                entry.data.get(CONF_DEBRID_PROVIDER, DEFAULT_DEBRID_PROVIDER)
            )
            existing_key = str(entry.data.get(CONF_DEBRID_API_KEY, "")).strip()
            api_key = entered_key or (
                existing_key if provider == existing_provider else ""
            )
            if provider != "none" and not api_key:
                errors[CONF_DEBRID_API_KEY] = "debrid_key_required"
            else:
                self._pending_data = {
                    **entry.data,
                    CONF_PACKAGE_NAME: str(user_input[CONF_PACKAGE_NAME]).strip(),
                    CONF_PROFILE_ID: user_input[CONF_PROFILE_ID],
                    CONF_STREAMING_PROVIDERS: list(
                        dict.fromkeys(
                            key
                            for value in user_input.get(CONF_STREAMING_PROVIDERS, [])
                            if (key := normalize_selected_provider(value))
                        )
                    ),
                    CONF_WATCHHUB_COUNTRY: str(
                        user_input.get(
                            CONF_WATCHHUB_COUNTRY,
                            entry.data.get(
                                CONF_WATCHHUB_COUNTRY,
                                getattr(self.hass.config, "country", None)
                                or DEFAULT_WATCHHUB_COUNTRY,
                            ),
                        )
                    ).upper(),
                    CONF_TMDB_ACCESS_TOKEN: tmdb_token,
                    CONF_TVDB_API_KEY: tvdb_key,
                    CONF_TVDB_SUBSCRIBER_PIN: tvdb_pin,
                    CONF_DEBRID_PROVIDER: provider,
                }

                if provider == "none":
                    self._pending_data.pop(CONF_DEBRID_API_KEY, None)
                else:
                    self._pending_data[CONF_DEBRID_API_KEY] = api_key

            if errors:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=self._reconfigure_schema(entry, user_input),
                    errors=errors,
                )

            self._connect_nuvio_after_justwatch = bool(
                user_input[CONF_CONNECT_ACCOUNT]
            )
            if user_input.get(CONF_MANAGE_JUSTWATCH_ACCOUNT, False):
                return await self.async_step_justwatch()

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

            if entry.data.get(CONF_REFRESH_TOKEN):
                return self.async_update_reload_and_abort(
                    entry,
                    data=self._pending_data,
                    title=entry.title,
                )

            try:
                return await self._async_start_account_login()
            except NuvioAuthError:
                errors["base"] = "login_start_failed"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._reconfigure_schema(entry, user_input),
            errors=errors,
        )

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm Nuvio device authorization without an indefinite spinner."""
        assert self._login is not None
        assert self._account_api is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                poll = await self._account_api.async_poll_device_login(self._login)
                status = str(poll.get("status", "")).lower()
                if status == "approved":
                    token_data = await self._account_api.async_exchange_device_login(
                        self._login
                    )
                    return self._finish_login(token_data)
                if status in {"expired", "used", "cancelled"}:
                    raise NuvioLoginExpired(f"Nuvio device login is {status}")
                errors["base"] = "login_pending"
            except NuvioLoginExpired:
                return self.async_abort(reason="login_failed")
            except NuvioAuthError:
                errors["base"] = "login_connection_failed"

        return self.async_show_form(
            step_id="device",
            data_schema=probatio.Schema(
                {
                    probatio.Optional("qr_code"): selector.QrCodeSelector(
                        config=selector.QrCodeSelectorConfig(
                            data=str(self._login["verification_uri_complete"]),
                            scale=6,
                            error_correction_level=selector.QrErrorCorrectionLevel.QUARTILE,
                        )
                    ),
                    probatio.Optional("authorization_code"): selector.ConstantSelector(
                        config=selector.ConstantSelectorConfig(
                            label="Authorization code",
                            value=str(self._login["user_code"]),
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "url": str(self._login["verification_uri_complete"]),
                "code": str(self._login["user_code"]),
            },
        )

    def _finish_login(self, token_data: dict[str, Any]) -> ConfigFlowResult:
        """Store the authorized renewable session."""
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
