# Nuvio for Home Assistant

A custom Home Assistant integration that exposes Stremio-compatible addon
catalogs in the Media browser and opens or plays the selected title in Nuvio on
an Android TV / Google TV device.

## Features

- Browse every `catalog` declared by one or more addon manifests.
- Sign in securely through Nuvio's device authorization page—no password is
  stored in Home Assistant.
- Browse the selected Nuvio profile's **Continue Watching** and **My Library**.
- Automatically load enabled addons synchronized with the selected profile.
- Search addons whose catalogs advertise the `search` extra.
- Browse a series by season and episode using the addon's `meta` resource.
- Open a movie, series, or episode with Nuvio's native `nuvio://` deep link.
- Start Nuvio's stream-selection/playback flow using the Android TV ADB
  integration and Nuvio's own `launchMode=stream` intent contract.
- English and Spanish UI strings.

## Install

### Manual

1. Copy `custom_components/nuvio` into Home Assistant's `/config/custom_components/`.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Nuvio**.
4. Enter one addon manifest URL per line. A Cinemeta URL is supplied by default.
5. Leave **Connect Nuvio account** enabled, select the profile number, then open
   the displayed Nuvio authorization URL (or scan its QR code), approve the
   code, and return to Home Assistant to select **Submit**.
6. Pick the Nuvio package installed on the TV. Play Store builds normally use
   `com.nuvio.app`; GitHub/sideload builds normally use `com.nuvio.tv`.

### HACS custom repository

Add the repository URL as an **Integration** custom repository, install Nuvio,
restart Home Assistant, and complete the same config flow.

## Home Assistant requirements

For catalog browsing and **Open title**, use an Android TV Remote media player
that accepts deep links through `media_player.play_media`.

For direct **Play** on Android TV, also configure the ADB-based **Android TV** integration for
the device. The `nuvio.play` action sends Nuvio's explicit Android intent through
`androidtv.adb_command`.

For **LG webOS**, configure Home Assistant's **LG webOS TV** integration and install
Nuvio TV (`space.nuvio.webos`) on the television. The Nuvio card detects webOS
players and launches Nuvio TV through `webostv.command` using
`system.launcher/launch`. Home Assistant sends the selected title/episode metadata
as webOS launch parameters. The current upstream Nuvio TV webOS build does not yet
consume those parameters for automatic detail-page or stream navigation, so today
LG support launches Nuvio TV rather than jumping directly into the selected title.
The integration is already structured for that behavior to become direct once the
webOS app implements launch-parameter routing.


## Lovelace card

Version 0.3.0 adds a bundled dashboard card. After updating the integration and
restarting Home Assistant, add it from the dashboard card picker as **Nuvio** or
use YAML:

```yaml
type: custom:nuvio-card
title: Nuvio
default_player: media_player.living_room_android_tv
columns: 6
show_search: true
```

The card provides horizontal catalog rows, search, title details, seasons and
episodes, a media-player selector, **Open in Nuvio**, and direct **Play** for
ADB-based Android TV entities. The frontend is served by the integration itself. Since v0.3.2 the integration also
registers the card as a Lovelace module resource with a versioned URL, avoiding stale
mobile/browser caches and `Custom element doesn't exist: nuvio-card` errors.

## Actions

Open a details page (movie):

```yaml
action: nuvio.open
target:
  entity_id: media_player.living_room_tv
data:
  media_type: movie
  content_id: tt16311594
```

Open a series:

```yaml
action: nuvio.open
target:
  entity_id: media_player.living_room_tv
data:
  media_type: series
  content_id: tt0903747
```

Direct playback (movie):

```yaml
action: nuvio.play
target:
  entity_id: media_player.living_room_android_tv
data:
  media_type: movie
  content_id: tt16311594
  title: Project Hail Mary
```

Direct playback (episode):

```yaml
action: nuvio.play
target:
  entity_id: media_player.living_room_android_tv
data:
  media_type: series
  content_id: tt0903747
  video_id: tt0903747:2:4
  title: Breaking Bad
  season: 2
  episode: 4
  episode_title: Down
```

`video_id` is the episode ID returned by the metadata addon. If omitted for a
movie it defaults to `content_id`. For a series episode, provide it whenever the
addon's ID is not exactly `content_id:season:episode`.



## Play in Nuvio vs direct playback

The card offers both playback paths on the **Sources** screen:

- **Open in Nuvio** opens Nuvio's stream screen for the selected movie/episode.
  Nuvio then uses its own synced addon/debrid configuration. Current Nuvio TV
  launch intents can target the movie/episode stream screen, but do not accept
  an individual preselected stream row, so the exact source is still selected
  inside Nuvio.
- **Play direct** uses the exact HTTP/HLS file URL. For torrent/debrid sources,
  Home Assistant can resolve the URL with credentials synchronized to the Nuvio
  account through Nuvio's provider-credential sync endpoint. The credential is
  kept server-side/in memory and is never returned to the Lovelace card.
  Raw signed stream URLs are intentionally hidden from the card layout.

A locally entered debrid token in Nuvio's Home Assistant reconfigure screen is
only an optional override/fallback; it is not required when the linked Nuvio
profile already has a supported synced credential.

## Debrid link resolution

Nuvio synchronizes provider credentials separately from the ordinary profile
settings blob. When a Nuvio account is linked, Home Assistant now pulls the
supported debrid credentials for the selected profile and uses them only on the
backend to turn torrent/debrid results into final HTTP file URLs. You can still
open **Settings → Devices & services → Nuvio → Reconfigure** and enter a local
provider/token as an optional override or fallback.

Supported resolvers:

- **TorBox**
- **Premiumize**
- **Real-Debrid**

The credential is stored locally in the Home Assistant config entry and is never
sent to the Lovelace card. The card sends only the torrent hash/magnet metadata
back to the integration for resolution.

On the **Sources** screen, unresolved torrent results get a **Resolve link**
button. If a provider is configured, **Resolve up to 6 links** resolves a small
batch without flooding the provider API. Once resolved, the row exposes the
final HTTP URL with **Play**, **Open link**, and **Copy link** actions. Resolved
links are cached in memory for 15 minutes.

## Media browser behavior

Selecting **Play** on a Media browser item resolves to Nuvio's public deep link,
which opens the matching details page. Home Assistant's media-source contract
resolves URLs; it cannot attach arbitrary Android intent extras. Use
`nuvio.play` for direct stream resolution/playback.

## Notes

- This integration reads catalog and metadata only. Stream URLs and debrid
  credentials stay in Nuvio and its configured addons.
- Account login uses Nuvio's public device authorization flow. Home Assistant
  stores renewable access/refresh tokens in its config entry, never the account
  password.
- Profile `1` is Nuvio's primary profile. Select `2`–`5` during setup when the
  desired profile uses another index.
- Addon servers must be reachable from Home Assistant.
- Only `http` and `https` manifest URLs are accepted.
- LG webOS app launching is supported. Direct title/episode routing depends on the upstream Nuvio TV webOS app adding launch-parameter handling.
