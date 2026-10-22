# Validation

- The AMD64 Docker image builds successfully using a multi-stage build pulling `alexxit/go2rtc:1.9.9` into `quantumentangledandy/neolink:latest`.
- Configuration validation rejects blank credentials, invalid camera names, invalid stream names and invalid ports.
- Password serialization handles quotes, backslashes, newlines, and UTF-8 characters across both TOML (Neolink) and YAML (go2rtc).
- The generated Neolink configuration binds to loopback (`127.0.0.1:38554`) with authenticated RTSP and local-only discovery.
- The generated go2rtc configuration binds to the configured external RTSP port (`28554`) and HTTP API port (`1984`), mapping both `/<name>` and `/<name>/<stream>` paths to Neolink's loopback stream.
- File descriptor limits (`nofile` ulimit to 65536 and runtime `RLIMIT_NOFILE`) are applied to prevent GLib `Creating pipes for GWakeup: Too many open files` aborts during client polling.
- Unit tests (`tests/test_config.py`) pass covering Neolink config generation, go2rtc stream mapping, custom ports, credential escaping, validation rules, and occupied port detection.
- Version 0.1.0/0.1.1 was installed under Home Assistant OS on an AMD64 VM.
- Version 0.1.2 resolves the file-descriptor exhaustion and connection-storm issue by placing go2rtc in front of Neolink and providing an HTTP snapshot URL for Generic Camera.
- Version 0.1.4 adds `ffmpeg` to the Docker image so `go2rtc` can generate JPEG snapshots for `/api/frame.jpeg`.
- Version 0.1.5 resolves the post-restart `TIME_WAIT` crash loop (`Address already in use`) by setting `SO_REUSEADDR` on port probes, retrying transiently busy ports, and disabling the unused WebRTC listener.
