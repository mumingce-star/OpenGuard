FROM python:3.12-slim

ENV OPENGUARD_CONTAINER_MODE=1 \
    OPENGUARD_PYTHON=/opt/openguard-venv/bin/python \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 openguard \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin openguard \
    && python -m venv /opt/openguard-venv

WORKDIR /app
COPY deployment/requirements.lock deployment/requirements.lock
RUN /opt/openguard-venv/bin/python -m pip install --disable-pip-version-check \
    --only-binary=:all: --no-cache-dir -r deployment/requirements.lock

COPY . /app/
RUN chmod 0444 samples/http-server.bundle \
    && install -d -m 0700 -o openguard -g openguard /app/runtime

USER openguard
RUN /opt/openguard-venv/bin/python -B openguard.py check

EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["/opt/openguard-venv/bin/python", "-B", "-c", "import json, urllib.request; errors = urllib.request.HTTPErrorProcessor(); errors.http_response = lambda request, response: response; opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), errors); response = opener.open('http://127.0.0.1:8000/healthz', timeout=3); raise SystemExit(0 if response.status == 200 and json.load(response).get('status') == 'ok' else 1)"]
CMD ["/opt/openguard-venv/bin/python", "-B", "openguard.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
