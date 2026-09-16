"""Constants for the Nuvio integration."""

from typing import Final

DOMAIN: Final = "nuvio"
CONF_MANIFEST_URLS: Final = "manifest_urls"
CONF_PACKAGE_NAME: Final = "package_name"

DEFAULT_MANIFEST_URL: Final = "https://v3-cinemeta.strem.io/manifest.json"
DEFAULT_PACKAGE_NAME: Final = "com.nuvio.app"
NUVIO_ACTIVITY: Final = "com.nuvio.tv.MainActivity"

SERVICE_OPEN: Final = "open"
SERVICE_PLAY: Final = "play"

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

DATA_API: Final = "api"
