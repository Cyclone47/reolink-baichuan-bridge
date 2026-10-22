# Validation

- The AMD64 Docker image built successfully from the supplied Dockerfile.
- Configuration validation rejected blank credentials, invalid camera names, invalid stream names and invalid ports.
- A password containing quotes, a backslash and a newline survived TOML serialization unchanged.
- The generated Neolink configuration used authenticated RTSP and local-only discovery; cloud push registration was disabled.
- The generated credential file had Unix permissions 0600.
- The built image authenticated to the actual doorbell and FFmpeg decoded eight seconds of its live video successfully. On Windows this test used the local UDP relay to cross Docker Desktop networking. The Linux host-network path has not been tested on the target VM.
- The Windows bridge's session-isolation repair separately passed a 130-second continuous video decode with no FFmpeg errors.
- Installation and camera-entity setup under the user's Home Assistant Supervisor remain to be performed.
- ARM64 runtime has not been tested.

These checks establish a working container and actual video conversion; they do not establish long-term reliability or battery consumption on the target Home Assistant VM.
