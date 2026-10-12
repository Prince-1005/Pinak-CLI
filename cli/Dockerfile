# Pinak CLI — containerized media downloader (ffmpeg included via apt).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System ffmpeg (no bundled .exe needed inside the container).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml CLI_README.md ./
COPY pinak ./pinak
COPY pinak_cli.py ./

RUN pip install --upgrade pip \
    && pip install .

# Default downloads volume.
VOLUME ["/downloads"]
ENV PINAK_OUTPUT_DIR=/downloads

ENTRYPOINT ["pinak"]
CMD ["--help"]
