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
   `com.nuvio.app`; standard GitHub/release builds use `com.nuvio.tv`. The
   HA-compatible Android build published by `fVaqueroG/NuvioTV` uses
   `com.nuvio.tv.ha`, allowing it to coexist with the official app.

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
Nuvio TV (`space.nuvio.webos`) on the television. HA-compatible
`NuvioTVSmart` builds consume `launchMode=player` plus the resolved
`streamUrl`, so **Play in Nuvio** can jump directly into Nuvio's internal
player for the exact source selected in the card.


### HA-compatible Nuvio app builds

For exact **Play in Nuvio** behavior, install the matching fork build:

- Android TV: `fVaqueroG/NuvioTV` → **HA Direct Play Android Build**. The
  Obtainium-compatible APK package is `com.nuvio.tv.ha`; set this value in
  **Nuvio → Reconfigure → Package name**. The workflow publishes normal GitHub
  Releases when the persistent signing-key secret is configured, so Obtainium
  can install and update the fork directly from the repository.
- LG webOS: `fVaqueroG/NuvioTVSmart` → **HA Direct Play webOS Build** artifact
  `nuvio-ha-direct-play-webos`. Its application id remains
  `space.nuvio.webos` and the fork also publishes a Homebrew Channel feed.

These builds accept `launchMode=player` and the exact resolved `streamUrl`.
Android also receives the selected HA profile id and stream metadata. webOS
queues the launch through profile/PIN selection when necessary, then enters the
player after the profile is activated.

### Nuvio Home mirroring

The bundled card mirrors the active Nuvio profile's synchronized Home composition:

- Home catalog order, disabled catalogs, and custom row titles
- pinned and ordered collection rows with their folder artwork/tile shapes
- Hero visibility and selected Hero catalog sources
- Continue Watching visibility, card-layout preferences, and episode thumbnails
- Nuvio watched-history based Next Up / Upcoming rows and Continue Watching sort mode
- release filtering, poster labels, catalog type suffixes, and Modern landscape-poster preference

The Home Assistant header/player/remote controls remain HA-specific. When Nuvio is configured to use an external tracking provider such as Trakt or Simkl for watch progress, provider-local progress that is not present in Nuvio's sync API can still make the app's dynamic Continue Watching row differ from the card.

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
show_remote: true
remote_side: left
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

- **Play in Nuvio** resolves the exact selected source and sends it to a
  compatible Nuvio app using `launchMode=player`. On Android this requires
  the ADB-based Android TV entity; on LG webOS it uses
  `system.launcher/launch`. The modified Nuvio apps then route the supplied
  `streamUrl` directly into their internal player.
- **Play on TV** sends the exact HTTP/HLS file URL to the television outside
  Nuvio. For torrent/debrid sources, Home Assistant can resolve the URL with
  credentials synchronized to the Nuvio account through Nuvio's
  provider-credential sync endpoint.
- If a source cannot be resolved to a URL, the Nuvio action falls back to
  opening that title/episode's source picker.

Raw signed stream URLs are intentionally hidden from the card layout.

A locally entered debrid token in Nuvio's Home Assistant reconfigure screen is
only an optional override/fallback; it is not required when the linked Nuvio
profile already has a supported synced credential.

## WatchHub series-link limitation

WatchHub currently exposes streaming-provider availability for series at the **show level**, not at a reliable season/episode level. Its episode requests can return the same provider URL for every episode of a series (for example, the same Netflix `/title/<series-id>` URL), so Home Assistant cannot derive a provider-specific Netflix episode id from WatchHub alone.

Nuvio still sends the selected `video_id`, season, episode, and episode title to provider launchers as contextual hints. WatchHub series-provider rows are labeled **Series-level** so the UI does not imply that the returned provider URL is episode-specific.

## JustWatch account session

Nuvio can use your **signed-in JustWatch account as the authoritative provider-link source**.

Configure it from **Settings → Devices & services → Nuvio → Reconfigure**:

1. Turn on **Manage JustWatch account** and submit.
2. Choose **Email & password (recommended)** for a normal JustWatch account.
3. Enter your JustWatch email and password. Nuvio exchanges them for Firebase session tokens and **does not store the password**.
4. Home Assistant stores the renewable JustWatch refresh/access tokens and refreshes the short-lived access token automatically.

For Google/Apple/social-login accounts that do not have a JustWatch password, choose **Google/Apple session token (advanced)**. That path accepts the current browser session token but cannot renew it without a refresh token.

Once connected:

- provider cards identify links as **JustWatch account**;
- authenticated requests explicitly request pre-affiliate offers and prefer `preAffiliatedStandardWebURL` over the affiliate/web URL;
- JustWatch-account provider links are authoritative: Nuvio does **not** silently substitute TheTVDB or WatchHub if the signed-in account does not return a usable link;
- selecting **Manage JustWatch account** again lets you reconnect or disconnect the saved JustWatch session.

JustWatch's official streaming-service documentation describes provider-supplied LG webOS deeplinks as an app `id` plus `params.contentTarget`. Those native LG payloads exist in JustWatch's streaming-service ingestion data, but the normal consumer GraphQL schema does not currently document a corresponding webOS field. Nuvio therefore uses the authenticated provider destination that the consumer account API actually exposes rather than guessing an undocumented field.

## Unofficial JustWatch offer links

Without a connected JustWatch account, Nuvio can still query JustWatch's unofficial web GraphQL endpoint anonymously for exact movie/episode provider offers. In that anonymous mode, TheTVDB and WatchHub remain fallback link sources.

For episodes, Nuvio searches the JustWatch show, resolves the requested season and episode node, and uses that episode's own offers rather than silently substituting a show-level URL. Any anonymous JustWatch failure is isolated so Sources and the provider row can continue using the configured fallbacks.

## TMDB / JustWatch availability row

Optionally configure a **TMDB API Read Access Token** from **Settings → Devices & services → Nuvio → Reconfigure** to add an **Available on** provider-logo row above Sources.

This row deliberately reuses the integration's existing filters instead of introducing separate TMDB settings:

- **WatchHub country** is used as the TMDB/JustWatch country/region.
- **Streaming providers** is used as the provider allow-list. Leaving it empty shows every streaming provider TMDB reports for the configured country.
- Movies use TMDB movie watch-provider availability.
- Series episodes use TMDB's **season-level** watch-provider availability for the selected season.

TMDB/JustWatch availability does **not** include full provider deep links, so Nuvio resolves playback links separately. When **TheTVDB API credentials** are configured, every provider-row load also resolves the exact TMDB movie/series/season/episode external IDs and queries TheTVDB v4 extended records for provider remote IDs. TheTVDB source-type `prefix` / `postfix` metadata is used to reconstruct the provider's canonical URL when available.

The provider row is independent of WatchHub. Its order is:

1. **TMDB/JustWatch** decides which providers are available in the configured **WatchHub country** and applies the configured **Streaming providers** allow-list.
2. Nuvio queries JustWatch's unofficial GraphQL endpoint for the exact movie or selected episode and prefers that provider's `standardWebURL`.
3. **TheTVDB** supplies the fallback exact provider URL when configured and JustWatch has no usable offer.
4. **WatchHub** is the final provider-link fallback.
5. If none supplies a usable provider URL, the TMDB provider logo remains visible as availability information but is disabled.

For series episodes, Nuvio resolves the JustWatch show → season → episode and reads the selected episode's own offers. TheTVDB's exact episode ID remains the next fallback when the JustWatch episode has no usable offer.

Availability data is supplied by **JustWatch via TMDB**. Exact external/provider-link metadata can be supplied by **TheTVDB**. This product uses the TMDB API but is not endorsed or certified by TMDB.

## Provider launch compatibility

Real-TV testing is authoritative for provider launch support. Apple TV direct title/episode launching is confirmed working on LG webOS and is deliberately left on its existing application-manager path.

For Netflix, Prime Video, Disney+, Max, Crunchyroll, and Paramount+, Nuvio now adapts the LG launch strategy used by **smartest-tv**:

- JustWatch `standardWebURL` values are unwrapped when JustWatch supplied an affiliate redirect, so the TV receives the provider's own URL.
- Nuvio does **not** close or restart provider apps. If the app is already running, the content launch/deeplink is sent directly to the existing app session; if it is not running, webOS launches it normally.
- The first LG request mirrors `aiowebostv.launch_app_with_content_id()`: `system.launcher/launch` with only `id` and `contentId`.
- Netflix uses `m=https://www.netflix.com/watch/<videoId>&source_type=4` when a numeric Netflix ID is available.
- Prime Video, Max, Crunchyroll, and Paramount+ receive the resolved provider URL itself as `contentId`.
- **Disney+** uses the LG Application Manager deep-link contract directly. Nuvio first tries app id `cdp-uwp-native` with `params.contentTarget=https://www.disneyplus.com/video/<UUID>` when a Disney UUID can be extracted, then retries the original JustWatch Disney URL and the installed `com.disney.disneyplus-prod` app-id variant.
- The older Nuvio provider-specific parameter bundle remains a service-level fallback for providers that still use the generic launcher path.
- LG native content search remains the final fallback when direct launch requests are rejected.

For Netflix episodes, an episode-specific JustWatch `/watch/<id>` offer can therefore be handed directly to Netflix as its own video ID. A show-level `/title/<id>` episode offer is still treated as insufficiently specific and uses the native-search fallback rather than pretending it identifies the requested episode.


## WatchHub provider launching

WatchHub provider links are launched in the installed streaming app rather than the TV/browser URL handler. Netflix keeps its proven title-id launch path. Prime Video, Disney+, Apple TV, Max, Crunchyroll, and Paramount+ now use provider-specific Android TV packages and LG webOS application launch parameters.

For Android TV, Nuvio explicitly targets the provider package so an HTTPS WatchHub link cannot be claimed by the browser. Prime Video GTI links are normalized to the Prime Video app-link format, and Max supports both current Android TV package variants.

For LG webOS, Nuvio sends provider-specific application-manager launch parameters (content target plus extracted provider title/entity ids) to the known provider app id. If a regional/legacy app id is unavailable, the integration tries the next known id and finally falls back to Home Assistant's installed-app source match.

When an episode-specific WatchHub request returns no results, Nuvio retries the series-level WatchHub id and labels those rows **Series-level**. This improves provider discovery for services whose WatchHub availability is exposed at show level while keeping true episode-level results authoritative when available.

## Source loading and addon filters

The Sources screen loads **WatchHub first** and renders those provider links before querying the remaining addons. Other addon groups then appear progressively below it.

The card header is persistent on every screen and keeps the card name visible. **Home**, **Refresh**, and **Control** remain at the top, and Sources adds an **Addons** button. Home returns to the cached Nuvio Home screen immediately without forcing a reload. The Addons button expands an **All + one chip per returned addon** filter row, matching the source-filter behavior used by the webOS app. Refreshing Sources repeats the WatchHub-first load.

## Streaming provider filtering

WatchHub provider links can be filtered from **Settings → Devices & services → Nuvio → Reconfigure** with two controls:

- **Streaming providers** filters the services that are shown. The same whitelist also filters provider folders in the synchronized **Streaming** collection so the Home row and title source list stay consistent.
- **WatchHub country** filters provider availability by country. It defaults to Home Assistant's configured country. The integration first tries WatchHub's country-specific endpoint and falls back to the normal endpoint plus Stremio `geos` / `countryWhitelist` hints when supplied.

The default provider whitelist is **Netflix, Prime Video, Disney+, and Max**, but the selector now includes a broad global catalog such as Apple TV+, Paramount+, Crunchyroll, **ViX, Mercado Play, Pluto TV, Claro video, Tubi, Plex, MUBI, Universal+, Runtime**, and many more. During reconfiguration the integration also discovers folders from the signed-in profile's synchronized **Streaming** collection and adds any provider names it finds. The selector accepts a custom provider value too, so a new WatchHub service does not require an integration update just to become filterable.

Provider names are normalized (for example, `Amazon Video` → Prime Video, `HBO Max` → Max, and `Mercado Play` → `mercado_play`), with the external URL hostname used as a fallback. Unknown provider names receive a stable generated key and can still be selected and filtered. Leaving the provider selection empty disables provider filtering and shows every WatchHub provider.

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
- Exact internal-player launch is supported by the HA-compatible Android and
  NuvioTVSmart fork builds. Older/unmodified app builds may only open Nuvio.

### Side remote

The card includes a compact, floating and collapsible TV remote for manual profile selection and recovery
from Nuvio's profile picker. It overlays the card instead of consuming catalog width. It supports directional navigation, OK, Back, Home,
and Wake. The Wake button also dismisses Android TV's screensaver when using the
ADB entity.

```yaml
show_remote: true
remote_side: left   # left or right
```

Set `remote_side: right` to place the controller on the right side of the
card, or `show_remote: false` to hide it.

### Collection folders and featured banner

Click any collection tile (for example **Streaming → Netflix**) to open its
saved addon catalogs. Use **All** or an individual source tab, then select a
title; **Back** returns to the same folder. Catalog headings and **See all**
open regular addon catalogs. Missing sources report an error without hiding
results from the other sources.

The featured banner rotates every seven seconds, with previous/next arrows
and a pause button. Rotation pauses on hover, keyboard focus, and hidden tabs,
and respects reduced-motion preferences. Optional card YAML settings:

```yaml
hero_autorotate: true
hero_interval: 7 # seconds, minimum 3
```

Frontend regression checks: `npm ci --prefix tests && node tests/test_card.cjs`.
