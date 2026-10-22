FROM alexxit/go2rtc:1.9.9 AS go2rtc-bin
FROM quantumentangledandy/neolink@sha256:4eebf499c20f8de740d8c32163f665e41fd0f342be3b1174828b3b8bd7def59d
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=go2rtc-bin /usr/local/bin/go2rtc /usr/local/bin/go2rtc
COPY run.py /usr/local/bin/reolink-bridge.py
ENTRYPOINT ["python3", "/usr/local/bin/reolink-bridge.py"]
