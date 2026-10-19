# Build from the extracted cloud bundle; no repository checkout is required.
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libportaudio2 gosu tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home pinak
WORKDIR /opt/pinak
COPY requirements-cloud-lock.txt ./
COPY *.whl ./
RUN python -m pip install --upgrade "pip>=26.2.1" "setuptools>=83.0.0" \
    && pip install --require-hashes -r requirements-cloud-lock.txt \
    && pip install --no-deps ./*.whl
COPY entrypoint.sh /usr/local/bin/pinak-cloud-entrypoint
RUN chmod 755 /usr/local/bin/pinak-cloud-entrypoint
ENV PINAK_CLOUD_DATA=/data PORT=8000
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/pinak-cloud-entrypoint"]
