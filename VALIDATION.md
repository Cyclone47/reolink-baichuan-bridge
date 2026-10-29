# Control Lab validation

- Sixteen passing Python tests cover capability/disruptive gating, numeric/enum validation, read-only enforcement, command allowlisting, read-back, MQTT discovery credential exclusion, non-retained snapshots, Ingress restrictions, CSRF enforcement, webhook source restrictions and bounded recording searches.
- A live read-only session authenticated to the doorbell, discovered 45 settings/sensors and returned state without read errors after targeted PIR/AI/chime queries. No setting setters, siren/reboot operations or webhook registration were executed against the physical device.
- MQTT discovery delivery, validated writes to a simulated device, retained-command replay protection and graceful offline publication passed against an ephemeral loopback-only broker.
- The localhost web panel was run against the real device with writes, MQTT and events disabled.
- Home Assistant Supervisor installation, Home Assistant entity creation from MQTT, actual webhook reception and ARM64 runtime still need target-host testing.
- Firmware-advertised write capabilities are not marked as verified merely because their read path works.
- Local Docker Desktop was unavailable during preparation. The branch includes a GitHub Actions image-build check; inspect its result before treating the container build as validated.
