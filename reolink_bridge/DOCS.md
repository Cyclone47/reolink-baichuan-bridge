# Reolink Stream Bridge

This app runs Neolink on the Home Assistant machine and converts the camera's local Baichuan stream into authenticated RTSP. It uses host networking for local UDP discovery. A Windows relay and the Reolink app are not needed on a normal Home Assistant OS installation.

## Configure

Set these options on the app's Configuration tab:

- `camera_name`: `doorbell` (this becomes the RTSP path).
- `camera_address`: camera LAN IP, for example `192.168.1.100`.
- `camera_uid`: the UID shown in Reolink device information; copy it exactly.
- `camera_username` and `camera_password`: the doorbell's local device credentials, not the cloud account.
- `stream`: start with `subStream`, which produced 1920 Ã— 1440 H.264 on the tested firmware. Stream names and resolutions may differ by firmware.
- `rtsp_port`: `18554`, or another unused port above 1023.
- `rtsp_username` and `rtsp_password`: choose separate credentials for the bridge output.
- `disconnect_when_idle`: keep enabled to allow the battery camera to sleep when no viewer is connected.

Save, start the app and enable Start on boot. Wait for the log to report that the camera is connected and the stream is available. Credentials are stored in the app's private data. Neolink may include the camera UID in its logs.

## Add a Home Assistant camera entity

1. Go to Settings â†’ Devices & services â†’ Add integration â†’ Generic Camera.
2. Leave Still Image URL empty.
3. Set Stream Source to `rtsp://127.0.0.1:18554/doorbell`.
4. Enter the bridge's `rtsp_username` and `rtsp_password` in the username/password fields. Choose TCP transport.
5. Finish setup and name the camera Doorbell. Add the resulting `camera.*` entity to a dashboard or use it in camera actions.

With Home Assistant OS, Core and this app use the host network, so the loopback URL is appropriate. You can also use the Home Assistant machine's LAN address. In other Docker arrangements, use an address reachable from the Home Assistant container. If the username/password fields do not work with your client, use `rtsp://USER:PASSWORD@HOST:18554/doorbell`, percent-encoding special characters in credentials.

The built-in `stream` integration is needed when only a stream URL is provided; normal Home Assistant configurations with `default_config:` include it. If your configuration omits it, add `stream:` and restart Home Assistant.

Home Assistant can create snapshots from the live stream. Snapshots and dashboard views may wake a battery camera. Avoid enabling stream preloading or leaving a live dashboard open continuously unless you intend to keep the camera awake.

## Scope and troubleshooting

This app provides a live video/audio source. It does not create motion, visitor, battery or two-way-talk entities. Those require additional integration work. It does not automatically create a camera entity; use Generic Camera as above.

The camera and HA host must be on a network that permits local UDP. Supply the camera IP if discovery broadcasts cannot cross a VLAN. Cloud discovery and push registration are disabled. No firmware modification or cloud account is required.

If you see timeouts, check the camera IP, local device password and VLAN/firewall rules. Wake-up from sleep can take a few seconds. If port 18554 is in use, change `rtsp_port` and the Generic Camera URL together. RTSP clients must authenticate.

The app is experimental. The wrapper and actual video stream can be tested in Docker; installation under your Home Assistant Supervisor and ARM64 runtime still require validation on the target host.

Upstream: https://github.com/QuantumEntangledAndy/neolink (AGPL-3.0). This package uses an unmodified upstream image pinned by digest.
