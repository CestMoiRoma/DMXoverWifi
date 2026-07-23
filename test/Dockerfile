# Test runner for the DMX over WiFi firmware.
#
# The board never enters this image. test/fake_esp32 stands in for the ESP32, so
# everything here is plain CPython plus a headless Chromium for the web UI tests.
#
# Build context is the repository root:
#   docker build -f test/Dockerfile -t dmx-wifi-tests .
FROM python:3.12-slim

# NODE_EXTRA_CA_CERTS: playwright downloads its browser through Node, which
# keeps its own CA list and ignores the system one unless pointed at it.
# Harmless by default, required when test/certs/ is in play.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    NODE_EXTRA_CA_CERTS=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# Escape hatch for machines behind TLS interception (corporate proxies, some
# antivirus products). Drop the intercepting root CA as a .crt into test/certs/
# and it gets trusted here; leave the directory empty and nothing changes.
# See test/certs/README.md.
COPY test/certs/ /usr/local/share/ca-certificates/dmx-extra/
RUN if ls /usr/local/share/ca-certificates/dmx-extra/*.crt >/dev/null 2>&1; then \
        apt-get update && apt-get install -y --no-install-recommends ca-certificates \
        && update-ca-certificates \
        && pip config set global.cert /etc/ssl/certs/ca-certificates.crt \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Dependencies first so edits to the firmware do not invalidate this layer.
COPY test/requirements.txt /app/test/requirements.txt
RUN pip install --no-cache-dir -r test/requirements.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Only what the suite reads. lib/ holds .mpy blobs the fake hardware replaces,
# and data/ is board-side runtime state.
# tools/ is here because the suite checks that what the board exports as .env is
# what deploy.py can read back in.
COPY pytest.ini boot.py code.py .env.example /app/
COPY src /app/src
COPY www /app/www
COPY tools /app/tools
COPY test /app/test

CMD ["python", "-m", "pytest", "test", "-v"]
