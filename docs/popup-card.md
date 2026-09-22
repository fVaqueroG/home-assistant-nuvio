# Nuvio popup button Lovelace card

Starting with v0.4.68, the integration registers **Nuvio Popup Button** as a second card in the Home Assistant dashboard card picker. It uses the same versioned frontend resource as the regular **Nuvio** card, so no additional Lovelace resource or Browser Mod installation is required.

```yaml
type: custom:nuvio-popup-card
button_label: Nuvio
# button_icon: mdi:television-play  # Optional: use this icon instead of the logo
popup_width: wide  # normal, wide, or fullscreen
title: Nuvio
columns: 6
show_search: true
show_remote: true
remote_side: left
```

Select **Nuvio Popup Button** in the visual card editor to configure the button label, icon, player, rooms, TV/HDMI mappings, and the usual Nuvio settings. All the options from the full-size `custom:nuvio-card` (including `rooms`, `default_room`, `default_player`, `display_routes`) work in the popup card as well. Open the popup by clicking the compact dashboard button; close it with the X, the backdrop, or Escape. The catalog is scrollable inside the dialog and takes the available display area on narrow screens.

The full-size card remains independently available using `type: custom:nuvio-card`.

Popup size: select **Normal** (up to 850 px), **Wide** (default, up to 1180 px), or **Full screen** in the popup card visual editor. The YAML key is `popup_width`. On narrow/mobile displays, the popup fills the viewport regardless of the selected preset. This changes the dialog dimensions only; existing Nuvio player/room/HDMI options continue to work.

By default, the compact popup button displays the official Nuvio wordmark. Leave `button_icon` absent or empty to show the logo. Set `button_icon: mdi:television-play` (or another Home Assistant icon) to replace the logo with that icon. Clear the icon field in the visual editor to return to the logo. Existing saved cards with an explicit icon keep their chosen icon; remove `button_icon` to switch to the logo. When the logo appears with the default Nuvio label, the duplicate label is hidden; a custom label is still shown. If the remote image fails to load, the button falls back to the word Nuvio.

Popup launcher appearance: set `button_style: horizontal` (default official wordmark), `button_style: vertical` (official Nuvio mark stacked above the button label), or `button_style: icon_text` (MDI icon beside the button label). Choose the same values in the visual editor under **Button appearance**. For `icon_text`, set `button_icon: mdi:movie-open` to choose an icon, or omit it for the default TV icon. Existing cards with a saved `button_icon` and no `button_style` retain their icon + text layout; explicitly choosing Horizontal or Vertical overrides it. Vertical launcher uses a taller dashboard button; popup size remains controlled separately by `popup_width`.

Choose `button_style: logo_only` for an icon-sized launcher showing only the official Nuvio logo mark, with no text even when `button_label` is configured. The visual editor offers **Logo only** under **Button appearance**. This setting controls only the dashboard launcher; `popup_width` and existing rooms, TVs, and playback settings are unchanged.

**Local brand images:** The integration includes the official logo files under `custom_components/nuvio/frontend/assets/` and serves them through Home Assistant at `/nuvio/assets/wordmark.webp` and `/nuvio/assets/mark.png`. All launcher appearances and the full card header use these local assets rather than requesting logos from external websites. Browser cache headers and versioned image URLs allow reuse across dashboard loads and updates.
