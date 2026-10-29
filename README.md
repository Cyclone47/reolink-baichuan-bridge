# Reolink Control Lab — experimental branch

[![Add experimental repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FCyclone47%2Freolink-baichuan-bridge%23feature%2Fdoorbell-control-lab)

**Separate companion app for local Reolink controls, telemetry and Home Assistant MQTT entities.** Your existing video bridge stays in place, and `main` is unchanged.

The capability-driven web panel discovered 45 settings and sensors in a read-only device test, including volumes, LEDs, sensitivity, image/encoding settings and two chimes. It also offers optional event webhooks, snapshots, recording metadata search, quick replies and opt-in disruptive commands. Firmware flags are hints: beta firmware can still reject individual operations.

## Install

1. Add the experimental repository with the button above, or paste this into the app store's Repositories dialog:

   ```text
   https://github.com/Cyclone47/reolink-baichuan-bridge#feature/doorbell-control-lab
   ```

2. Install **Reolink Control Lab**. Keep the already-installed stream bridge; don't install a duplicate video bridge from this branch.
3. Enter the camera's local IP, UID, username and password in Configuration.
4. Start and choose Open Web UI. The first run is read-only, with polling and event registration off.
5. Optionally configure your MQTT broker to create Home Assistant entities automatically.
6. Enable writes only when ready. Siren/reboot/privacy/recording and other disruptive controls require a second explicit option.

[Full configuration and usage guide](reolink_control_lab/DOCS.md) · [Validation and limits](VALIDATION.md) · [Stable video bridge](https://github.com/Cyclone47/reolink-baichuan-bridge/tree/main)

This app implements the supported control surface, not every possible command. Two-way audio transport, custom TTS/upload, firmware updates, credential/network changes and recording playback/download are not implemented. No actual device identifiers, credentials or camera images are included in this repository.

## Development

```bash
python -m pip install -r reolink_control_lab/requirements.txt
python -m pip install -r tests/requirements.txt
python -m unittest discover -s tests -p "test_control_lab*.py" -v
docker build -t reolink-control-lab reolink_control_lab
```

The original stable video-bridge files remain on this branch because it branches from the existing repository. The new companion has its own slug and image; it is not merged into `main`.

Protocol implementation: [reolink_aio](https://github.com/starkillerOG/reolink_aio) (MIT). Repository packaging follows the existing repository's AGPL-3.0 license. Independent community project, not affiliated with Reolink or Home Assistant.
