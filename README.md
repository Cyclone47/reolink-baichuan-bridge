# Reolink Baichuan Bridge

**Bring a Reolink camera's local video stream into Home Assistant—even when the camera does not expose RTSP.**

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FCyclone47%2Freolink-baichuan-bridge)
[![Add Generic Camera](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=generic)

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Status](https://img.shields.io/badge/status-experimental-orange)
![Architectures](https://img.shields.io/badge/architectures-amd64%20%7C%20aarch64-blue)
[![License](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

A Home Assistant app (formerly called an add-on) that wraps [Neolink](https://github.com/QuantumEntangledAndy/neolink), translating Reolink's proprietary Baichuan protocol into an authenticated RTSP stream. Add that stream through Home Assistant's built-in **Generic Camera** integration to get a normal `camera.*` entity.

```text
Reolink camera → local Baichuan UDP → Neolink → authenticated RTSP → Home Assistant camera
```

## What you get

- Local video and supported audio, without keeping the Reolink desktop app open.
- Configuration through the Home Assistant app UI.
- Separate credentials for the camera and the RTSP output.
- Local-only camera discovery; cloud discovery and push registration are disabled.
- On-demand streaming and idle disconnection for battery cameras.
- A pinned upstream image, plus a Docker Compose option for Linux hosts.

**Experimental:** AMD64 container build, authentication and live video decoding have been tested. Installation under Home Assistant Supervisor, direct Linux host networking and ARM64 runtime still need target-host validation. Compatibility depends on your camera and firmware; this is not a promise that every Reolink model works. See [validation details](VALIDATION.md).

## Requirements

- **Home Assistant OS** with the app/add-on store. A Proxmox VM running Home Assistant OS is suitable.
- A supported AMD64 or ARM64 host.
- A camera reachable over the local network, with its UID and local device credentials.
- An unused TCP port for RTSP; the default is **18554**.

This is an app-store repository, so **HACS is not used**. Home Assistant Container users can use [Docker Compose](#docker-compose-for-home-assistant-container).

## 1. Install the app

Click **Add repository to Home Assistant** above and confirm the repository URL. Your My Home Assistant instance URL must point to your own HA installation.

Or add the repository manually:

1. Open **Settings → Apps → Install app** (older versions: **Settings → Add-ons → Add-on Store**).
2. Open **⋮ → Repositories**.
3. Add `https://github.com/Cyclone47/reolink-baichuan-bridge`.
4. Refresh/check for updates, then select **Reolink Stream Bridge** and choose **Install**.

The first installation builds the container on your HA host and downloads its dependencies. No prebuilt project image is required.

## 2. Configure the bridge

On the app's **Configuration** tab, enter your own values:

```yaml
camera_name: doorbell
camera_address: "192.168.1.100"
camera_uid: "COPY_YOUR_DEVICE_UID"
camera_username: admin
camera_password: "YOUR_LOCAL_DEVICE_PASSWORD"
stream: subStream
rtsp_port: 18554
rtsp_username: homeassistant
rtsp_password: "CHOOSE_A_SEPARATE_STREAM_PASSWORD"
disconnect_when_idle: true
```

Use the password for the **camera itself**, not your Reolink cloud account. Copy the UID exactly from device information in the Reolink app. Start with `subStream`; its actual resolution varies by firmware.

Save, start the app and enable **Start on boot**. Check the **Log** tab for a successful login and an available stream. Wake-up and startup can take a few seconds.

## 3. Add your camera to Home Assistant

Click **Add Generic Camera** above, or use **Settings → Devices & services → Add integration → Generic Camera**.

| Field | Value |
| --- | --- |
| Still Image URL | Leave empty |
| Stream Source | `rtsp://127.0.0.1:18554/doorbell` |
| Username | Your bridge `rtsp_username` |
| Password | Your bridge `rtsp_password` |
| RTSP transport | TCP |

The loopback address applies when the app and Home Assistant Core share the HA OS host network. If needed, replace `127.0.0.1` with the HA machine's LAN IP. If you change `camera_name` or `rtsp_port`, update the URL too.

Home Assistant's `stream` integration is needed when no still-image URL is supplied. Normal configurations with `default_config:` include it. Otherwise, add `stream:` to your HA configuration and restart Home Assistant.

Finish setup and give the camera a name. Your resulting entity might be `camera.doorbell`; use the actual entity ID shown in your installation.

### Dashboard example

```yaml
type: picture-entity
entity: camera.doorbell
camera_view: auto
show_name: true
show_state: false
```

For continuous live viewing, use `camera_view: live`. This keeps a battery camera awake and consumes battery. Leave stream preloading off unless you intend to keep the camera awake.

The camera entity can also be used with normal Home Assistant camera actions. When using snapshots, remember that fetching an image may wake the camera. This app does not provide a standalone media-library browser.

## Docker Compose for Home Assistant Container

On a **Linux** host:

```bash
git clone https://github.com/Cyclone47/reolink-baichuan-bridge.git
cd reolink-baichuan-bridge
cp options.example.json options.json
# Edit options.json with your camera credentials and a separate RTSP password.
docker compose up -d --build
```

The Compose file uses host networking for UDP discovery. Add the stream with Generic Camera using an address reachable from your Home Assistant container. Windows Docker Desktop networking needs additional relay handling and is not covered by this Compose deployment.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Repository does not appear | Confirm HA OS/app-store support, repository URL, then refresh the store. |
| Login rejected | Verify the local device username/password; cloud credentials are different. |
| Discovery times out | Check the UID, camera IP and local UDP/VLAN connectivity. |
| Stream unavailable immediately after starting | Wait a few seconds for discovery/login, then retry. |
| RTSP says unauthorized | Use the bridge credentials, not the camera credentials. |
| Port already in use | Change `rtsp_port` and update the Generic Camera URL. |
| Battery drains | Close live dashboards, disable preloading and keep idle disconnection enabled. |

See the [full configuration guide](reolink_bridge/DOCS.md). For updates, refresh the app store and install an offered update; restart the app afterwards. To remove it, remove the Generic Camera entry and stop/uninstall the app. You can then remove this repository from the store.

## Scope and privacy

This provides a live stream, not motion, visitor, battery or two-way-talk entities. Those require additional integration work. No firmware modification is required. The bridge runs locally; it does not change the camera's own independent cloud settings.

No personal credentials, device identifiers, camera captures or firmware files are included. `options.json` and local credential files are git-ignored. Neolink logs can include a device UID, so redact logs before sharing an issue. Keep the RTSP endpoint on a trusted network.

## Credits and license

The protocol implementation and RTSP server are provided by [QuantumEntangledAndy/Neolink](https://github.com/QuantumEntangledAndy/neolink), based on [thirtythreeforty/Neolink](https://github.com/thirtythreeforty/neolink). This repository adds Home Assistant packaging and configuration; it uses an unmodified upstream image pinned by digest.

Licensed under [AGPL-3.0](LICENSE). Independent community project; not affiliated with Reolink or Home Assistant.
