# Changelog

## 0.1.4

- Install `ffmpeg` in Docker image so `go2rtc` can transcode video keyframes into JPEG snapshots for `/api/frame.jpeg`.

## 0.1.3

- Change default HTTP snapshot/API port to `21984` to avoid collisions with standard `go2rtc` or Frigate installations (which occupy port 1984 on host network).
- Add automatic fallback from port 1984 to `21984` if port 1984 is already occupied by another service on the host.

## 0.1.2

- Bundle `go2rtc` (v1.9.9) as an internal RTSP multiplexer and snapshot provider to prevent connection storms and GStreamer file descriptor exhaustion (`GLib-ERROR: Creating pipes for GWakeup: Too many open files`).
- Provide an HTTP snapshot API on port 1984 (`http://127.0.0.1:1984/api/frame.jpeg?src=<camera_name>`) for Home Assistant Generic Camera's Still Image URL.
- Increase file descriptor limits (`ulimits.nofile: 65536` in `config.yaml` and runtime `RLIMIT_NOFILE` adjustment in supervisor).
- Map both `/<name>` and `/<name>/<stream>` paths through go2rtc RTSP proxy.
- Supervise both Neolink (bound to loopback port 38554) and go2rtc (bound to RTSP port 28554 and API port 1984) with graceful process shutdown.

## 0.1.1

- Check that the configured RTSP port can bind before starting Neolink, with an actionable error for occupied ports.
- Use port 28554 for new installations. Existing saved port settings are preserved.
- Clarify that Generic Camera must use the RTSP credentials saved in the app, and document the explicit substream URL.
- Add regression tests for occupied ports and credential serialization.

## 0.1.0

- Initial Home Assistant app packaging for the Neolink Baichuan-to-RTSP bridge.
- Local-only discovery, separate RTSP credentials and configurable idle disconnection.
- AMD64 and ARM64 image support; AMD64 build and real-camera stream tested locally.
- Linux Docker Compose deployment and Generic Camera setup instructions.
