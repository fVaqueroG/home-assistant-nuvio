# Nuvio popup button Lovelace card

Starting with v0.4.68, the integration registers **Nuvio Popup Button** as a second card in the Home Assistant dashboard card picker. It uses the same versioned frontend resource as the regular **Nuvio** card, so no additional Lovelace resource or Browser Mod installation is required.

```yaml
type: custom:nuvio-popup-card
button_label: Nuvio
button_icon: mdi:television-play
title: Nuvio
columns: 6
show_search: true
show_remote: true
remote_side: left
```

Select **Nuvio Popup Button** in the visual card editor to configure the button label, icon, player, rooms, TV/HDMI mappings, and the usual Nuvio settings. All the options from the full-size `custom:nuvio-card` (including `rooms`, `default_room`, `default_player`, `display_routes`) work in the popup card as well. Open the popup by clicking the compact dashboard button; close it with the X, the backdrop, or Escape. The catalog is scrollable inside the dialog and takes the available display area on narrow screens.

The full-size card remains independently available using `type: custom:nuvio-card`.
