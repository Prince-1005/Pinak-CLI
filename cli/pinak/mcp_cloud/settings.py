"""Explicit, validated operator settings for a single cloud instance."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: Path
    public_url: str
    max_users: int = Field(default=20, ge=1, le=100)
    storage_bytes: int = Field(default=10 * 1024**3, ge=1024**2)
    max_jobs: int = Field(default=1000, ge=1, le=10000)
    link_seconds: int = Field(default=300, ge=30, le=3600)
    calls_per_minute: int = Field(default=120, ge=1, le=10000)
    allow_insecure_loopback: bool = False

    @model_validator(mode="after")
    def validate_location(self) -> Settings:
        parsed = urlsplit(self.public_url)
        if (
            parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not parsed.hostname
        ):
            raise ValueError("public_url must be an origin, without credentials, path or query")
        if parsed.scheme != "https" and not (
            self.allow_insecure_loopback
            and parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError("public_url requires HTTPS; HTTP is only for explicit loopback tests")
        self.public_url = self.public_url.rstrip("/")
        if not self.data_dir.is_absolute():
            raise ValueError("data_dir must be absolute")
        self.data_dir = self.data_dir.resolve()
        return self

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            data_dir=Path(os.environ.get("PINAK_CLOUD_DATA", "/data")),
            public_url=os.environ.get("PINAK_CLOUD_URL", ""),
            max_users=int(os.environ.get("PINAK_CLOUD_MAX_USERS", "20")),
            storage_bytes=int(os.environ.get("PINAK_CLOUD_STORAGE_BYTES", str(10 * 1024**3))),
            max_jobs=int(os.environ.get("PINAK_CLOUD_MAX_JOBS", "1000")),
            calls_per_minute=int(os.environ.get("PINAK_CLOUD_CALLS_PER_MINUTE", "120")),
            link_seconds=int(os.environ.get("PINAK_CLOUD_LINK_SECONDS", "300")),
            allow_insecure_loopback=os.environ.get("PINAK_CLOUD_TEST_LOOPBACK") == "1",
        )
