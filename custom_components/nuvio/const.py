"""Constants for the Nuvio integration."""

from typing import Final

DOMAIN: Final = "nuvio"
CONF_MANIFEST_URLS: Final = "manifest_urls"
CONF_PACKAGE_NAME: Final = "package_name"
CONF_CONNECT_ACCOUNT: Final = "connect_account"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_PROFILE_ID: Final = "profile_id"
CONF_USER_ID: Final = "user_id"
CONF_EMAIL: Final = "email"

DEFAULT_MANIFEST_URL: Final = "https://v3-cinemeta.strem.io/manifest.json"
DEFAULT_PACKAGE_NAME: Final = "com.nuvio.app"
DEFAULT_PROFILE_ID: Final = 1
NUVIO_ACTIVITY: Final = "com.nuvio.tv.MainActivity"
NUVIO_WEBOS_APP_ID: Final = "space.nuvio.webos"

NUVIO_BACKEND_URL: Final = "https://api.nuvio.tv"
# Nuvio's public Supabase publishable key, also distributed in the Nuvio client.
NUVIO_API_KEY: Final = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJyb2xlIjoiYW5vbiIsImlzcyI6InN1cGFiYXNlIiwiaWF0IjoxNzgxNTIxMzQ2LCJleHAiOjE5MzkyMDEzNDZ9."
    "tmQaj682pwzehpqlgCDMnySOqiUvpgRbrE43T4VJpDI"
)

SERVICE_OPEN: Final = "open"
SERVICE_PLAY: Final = "play"
SERVICE_PLAY_SOURCE: Final = "play_source"

ATTR_CONTENT_ID: Final = "content_id"
ATTR_MEDIA_TYPE: Final = "media_type"
ATTR_VIDEO_ID: Final = "video_id"
ATTR_TITLE: Final = "title"
ATTR_POSTER: Final = "poster"
ATTR_BACKDROP: Final = "backdrop"
ATTR_LOGO: Final = "logo"
ATTR_SEASON: Final = "season"
ATTR_EPISODE: Final = "episode"
ATTR_EPISODE_TITLE: Final = "episode_title"
ATTR_STREAM_URL: Final = "stream_url"
ATTR_STREAM_TITLE: Final = "stream_title"
ATTR_MIME_TYPE: Final = "mime_type"

DATA_API: Final = "api"
DATA_ACCOUNT_API: Final = "account_api"
