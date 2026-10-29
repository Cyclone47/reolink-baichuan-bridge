# Reolink Control Lab

This experimental companion runs separately from Reolink Stream Bridge. It provides local device controls and telemetry through a Home Assistant Ingress panel and optional MQTT discovery. It does not replace the video bridge, modify its configuration, or automatically install a custom integration.

## Install from the experimental branch

Add this repository URL in Settings → Apps → Install app → ⋮ → Repositories:

```text
https://github.com/Cyclone47/reolink-baichuan-bridge#feature/doorbell-control-lab
```

Install **Reolink Control Lab**, not a second copy of Reolink Stream Bridge. Configure the camera address, UID, local username and local password. Start the app and choose Open Web UI. It starts in read-only mode with camera polling and event registration disabled.

The first installation builds the image on the HA host. AMD64 and ARM64 are declared; only the tested platforms listed in VALIDATION.md should be treated as validated.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| `camera_name` | Doorbell | Name of the MQTT device |
| `camera_address` | empty | Camera's literal IPv4/IPv6 address; required |
| `camera_uid` | empty | Device UID; auto-discovered locally if omitted |
| `camera_username` | admin | Local camera account |
| `camera_password` | empty | Local camera password; required |
| `camera_channel` | 0 | Standalone doorbell channel |
| `read_only` | true | Blocks camera-setting commands; refresh, snapshots and search remain available |
| `allow_disruptive_actions` | false | Exposes siren/reboot/privacy/recording/PIR/notification/work-mode controls and announcement playback |
| `enable_events` | false | Registers this app as the camera's webhook receiver; requires read-only mode off |
| `replace_existing_webhook` | false | Explicitly permits replacing an existing camera webhook |
| `poll_interval` | 0 | 0 = manual only; otherwise at least 60 seconds between camera reads |
| `mqtt_host` | empty | Optional MQTT broker; empty means web panel only |
| `mqtt_port` | 1883 | Broker port; commonly 8883 with TLS |
| `mqtt_username` | empty | Broker account |
| `mqtt_password` | empty | Broker password |
| `mqtt_tls` | false | Enable TLS with normal certificate verification |

The UI reads cached state every five seconds; that does **not** poll or wake the camera. Starting the app performs one discovery/read. Read camera now, a command, snapshot, search or configured polling can wake it. Availability means the last camera read succeeded, not a continuously maintained health check.

## What gets exposed

Only controls gated by camera capabilities and available options appear. The local read test discovered 45 settings/sensors on the tested firmware; that number varies. Unknown and rejected reads stay visible as unknown/errors instead of being treated as measured zeroes.

- Battery percentage/temperature and sleep state; Wi-Fi signal where available.
- Speaker, general and doorbell volumes, button sound, audio recording.
- Status/doorbell LEDs, infrared, day/night, anti-flicker and image adjustments.
- PIR/motion sensitivity and AI sensitivity/delay for supported person/vehicle/pet/package classes.
- Main/substream bit-rate and frame-rate choices.
- Quick-reply selection, automatic-reply enable and delay. Playback needs stored reply files; no entries means playback is unavailable.
- Post-recording duration and reported battery/powered work modes.
- Chime volume, LEDs, silent time, tones and playback where the camera returns the required chime data.
- Optional disruptive controls: recording, privacy mode/masks, PIR, push/email/FTP toggles, siren-on-event, short siren, stop siren and reboot.
- Synchronize time button (only when writes are enabled).
- Snapshot action and a bounded last-24-hours recording metadata search.

Firmware advertisement is not proof that a setter works. Commands are serialized, range/enum checked and bounded by timeouts. The app reports the read-back/cache value; it never substitutes the requested value as a successful state. Not every command can supply immediate read-back; refresh if needed. Reboot and privacy can temporarily disconnect the camera.

## MQTT and Home Assistant entities

Configure a broker already integrated with Home Assistant, then restart the app. Discovery publishes under `homeassistant/`; one device named `<camera_name> Control Lab` appears under MQTT.

In read-only mode, controls appear as sensors and buttons that change settings are omitted. When read-only mode is disabled, supported writable values become number/select/switch/button entities. Old discovery topics owned by this app are removed when the entity type or capability set changes. The app republishes discovery when Home Assistant announces it is online.

State topics use a hashed local identifier; the raw camera UID/password are not published. Snapshot image data is sent only on demand and is **not retained**. Ordinary telemetry/discovery is retained. Commands replayed as retained messages on subscription are ignored. Configure broker authentication and network access appropriately for your LAN; this app does not set broker ACLs.

To remove the entities later, stop the app, use MQTT's device removal/discovery cleanup, and uninstall the app. Uninstall alone cannot delete retained broker messages after the container is gone.

## Events

Event subscription is opt-in because battery cameras may have a single webhook destination. Another Reolink integration can already own that slot. Existing active webhooks are preserved unless replacement is explicitly enabled. The app registers a camera-source-restricted, randomized URL and passes the payload to the upstream parser.

Doorbell/motion/AI MQTT binary states are five-second **event pulses**, not sustained presence detectors. They remain unknown while event handling is off. Event reception on the target HA host still needs a real ring/motion test.

On graceful shutdown, the app restores the previous webhook only if the camera still points at this app's URL. If another controller has replaced it, it is left untouched. A power loss/forced kill cannot run cleanup; you may need to re-register the previous owner's webhook manually.

## Security and privacy

The web panel accepts requests only from the Home Assistant Supervisor Ingress IP. It has CSRF protection for commands and does not expose a separately authenticated public/LAN web dashboard. Host networking is used for local camera UDP. The Supervisor allocates a free Ingress port to avoid the video bridge's port.

Credentials live in the app's private options. Errors redact the configured camera UID/password and MQTT password. No raw protocol console, arbitrary Python evaluation, firmware updater, user editor or network reconfiguration is provided.

## Explicit limits

This does not promise every possible doorbell function. Two-way audio transport, arbitrary TTS/audio upload, recording downloads/playback, firmware flashing, account changes and native RTSP/ONVIF enablement are not implemented. Keep the existing video bridge and Generic Camera entity for live video. Experimental advertising flags are shown in diagnostics so additional controls can be developed with evidence.

Upstream protocol library: https://github.com/starkillerOG/reolink_aio. Home Assistant MQTT discovery: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery.
