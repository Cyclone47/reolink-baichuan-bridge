# Reolink Stream Bridge

This app runs Neolink on the Home Assistant machine and converts the camera's local Baichuan stream into authenticated RTSP. It uses host networking for local UDP discovery. A Windows relay and the Reolink app are not needed on a normal Home Assistant OS installation.

`go2rtc` is bundled internally to multiplex RTSP connections and provide an HTTP snapshot endpoint, preventing FFmpeg connection storms and file descriptor leaks under Home Assistant dashboard polling.

## Configure

Set these options on the app's Configuration tab:

- `camera_name`: `doorbell` (this becomes the RTSP path).
- `camera_address`: your camera's local LAN IP address, for example `192.168.1.100` (see Reolink guide: [How to Find the IP Address of Reolink Device](https://support.reolink.com/articles/900007660243-How-to-Find-the-IP-Address-of-Reolink-Device/)).
- `camera_uid`: the UID shown in Reolink device information; copy it exactly (see Reolink guide: [How to Find the UID for Your Reolink Device](https://support.reolink.com/articles/900005185523-How-to-Find-the-UID-for-Your-Reolink-Device/)).
- `camera_username` and `camera_password`: the camera's local device credentials, not the cloud account.
- `stream`: choose `subStream` or `mainStream`. Stream names and supported resolutions differ by camera model and firmware.
- `rtsp_port`: `28554`, or another unused port above 1023.
- `api_port`: `21984`, or another unused port for HTTP snapshots.
- `rtsp_username` and `rtsp_password`: choose separate credentials for the bridge output.
- `disconnect_when_idle`: keep enabled to allow battery cameras to sleep when no viewer is connected (can be disabled for hardwired setups needing continuous streaming).

Save, start the app and enable Start on boot. Wait for the log to report that the camera is connected and the stream is available. Credentials are stored in the app's private data. Neolink may include the camera UID in its logs.

## Add a Home Assistant camera entity

1. Go to Settings → Devices & services → Add integration → Generic Camera.
2. Set Still Image URL to `http://127.0.0.1:21984/api/frame.jpeg?src=doorbell`.
   Using this endpoint allows Home Assistant to grab snapshots without spawning repeated RTSP streams.
3. Set Stream Source to `rtsp://127.0.0.1:28554/doorbell` (or `rtsp://127.0.0.1:28554/doorbell/subStream`).
4. Enter the bridge's `rtsp_username` and `rtsp_password` in the username/password fields. Choose TCP transport.
5. Finish setup and name the camera (e.g. Doorbell or Front Camera). Add the resulting `camera.*` entity to a dashboard or use it in camera actions.

With Home Assistant OS, Core and this app use the host network, so the loopback URL is appropriate. You can also use the Home Assistant machine's LAN address. In other Docker arrangements, use an address reachable from the Home Assistant container. If the username/password fields do not work with your client, use `rtsp://USER:PASSWORD@HOST:28554/doorbell`, percent-encoding special characters in credentials.

The built-in `stream` integration is needed when only a stream URL is provided; normal Home Assistant configurations with `default_config:` include it. If your configuration omits it, add `stream:` and restart Home Assistant.

Home Assistant can create snapshots from the live stream. Snapshots and dashboard views may wake a battery camera. Avoid enabling stream preloading or leaving a live dashboard open continuously unless you intend to keep the camera awake.

## Scope and troubleshooting

This app provides a live video/audio source. It does not create motion, visitor, battery or two-way-talk entities. Those require additional integration work. It does not automatically create a camera entity; use Generic Camera as above.

The camera and HA host must be on a network that permits local UDP. Supply the camera IP if discovery broadcasts cannot cross a VLAN. Cloud discovery and push registration are disabled. No firmware modification or cloud account is required.

If you see timeouts, check the camera IP, local device password and VLAN/firewall rules. Wake-up from sleep can take a few seconds. If port 28554 is in use, change `rtsp_port` and the Generic Camera URL together. RTSP clients must authenticate.

The app is experimental. The AMD64 image, installation under Home Assistant OS, and actual RTSP video have been tested. ARM64 runtime and long-term battery behavior still need validation. Startup checks detect occupied ports. Existing saved port settings are preserved on update, so change the port manually if an older configuration conflicts.

Upstream: https://github.com/QuantumEntangledAndy/neolink (AGPL-3.0) and https://github.com/AlexxIT/go2rtc.
