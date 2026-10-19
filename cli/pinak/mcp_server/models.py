"""Validated public inputs and user policy, independent of the optional SDK."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

import platformdirs
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

JobState = Literal["queued", "running", "succeeded", "skipped", "failed", "cancelled"]
PositiveID = Annotated[StrictInt, Field(ge=1)]
RequestKey = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)


class Policy(StrictModel):
    config_schema_version: Literal[1] = 1
    default_output_dir: Path = Field(default_factory=lambda: Path.home() / "Downloads" / "Pinak")
    output_roots: list[Path] | None = None
    read_roots: list[Path] = Field(default_factory=list)
    max_page_size: int = Field(default=100, ge=1, le=100)
    max_mutation_items: int = Field(default=100, ge=1, le=100)
    max_response_bytes: int = Field(default=102400, ge=4096, le=1048576)
    shutdown_grace_seconds: float = Field(default=10, ge=1, le=30)
    parent_heartbeat_seconds: float = Field(default=2, ge=0.1, le=5)
    orphan_threshold_seconds: float = Field(default=30, ge=1, le=120)
    mutation_receipt_retention_days: int = Field(default=7, ge=1, le=30)
    update_checks: Literal["manual"] = "manual"

    @model_validator(mode="after")
    def normalize(self) -> Policy:
        roots = self.output_roots if self.output_roots is not None else [self.default_output_dir]
        for path in [self.default_output_dir, *roots, *self.read_roots]:
            if not path.is_absolute():
                raise ValueError("Configured directories must be absolute paths")
        self.default_output_dir = self.default_output_dir.resolve()
        self.output_roots = [path.resolve() for path in roots]
        self.read_roots = [path.resolve() for path in self.read_roots]
        if not any(self.default_output_dir.is_relative_to(root) for root in self.output_roots):
            raise ValueError("default_output_dir must be inside an output root")
        if self.orphan_threshold_seconds <= self.parent_heartbeat_seconds * 2:
            raise ValueError("orphan threshold must exceed two heartbeat intervals")
        return self


def config_path() -> Path:
    value = os.environ.get("PINAK_MCP_CONFIG")
    return (
        Path(value).expanduser().absolute()
        if value
        else Path(platformdirs.user_config_dir("pinak-cli", "pinak")) / "mcp.json"
    )


def load_policy(path: Path | None = None) -> Policy:
    location = path or config_path()
    if location.exists():
        if location.stat().st_size > 65536:
            raise ValueError("MCP configuration exceeds 64 KiB")
        return Policy.model_validate_json(location.read_text(encoding="utf-8"))
    return Policy()


class Options(StrictModel):
    output_dir: str | None = Field(default=None, max_length=4096)
    quality: str | None = Field(default=None, max_length=32)
    audio: StrictBool = False
    force: StrictBool = False
    trim: str | None = Field(default=None, max_length=64)


class Add(StrictModel):
    url: str = Field(min_length=8, max_length=8192)
    options: Options = Field(default_factory=Options)
    request_key: RequestKey


class Page(StrictModel):
    cursor: PositiveID | None = None
    limit: Annotated[StrictInt, Field(ge=1, le=100)] = 25


class JobList(Page):
    status: JobState | None = None


class Show(Page):
    job_id: PositiveID


class IDs(StrictModel):
    job_ids: list[PositiveID] = Field(min_length=1, max_length=100)
    request_key: RequestKey


class Retry(StrictModel):
    job_ids: list[PositiveID] | None = Field(default=None, min_length=1, max_length=100)
    all_failed: StrictBool = False
    request_key: RequestKey

    @model_validator(mode="after")
    def target(self) -> Retry:
        if bool(self.job_ids) == self.all_failed:
            raise ValueError("Choose job_ids or all_failed, exclusively")
        return self


class Mutation(StrictModel):
    request_key: RequestKey


class Start(StrictModel):
    job_ids: list[PositiveID] | None = Field(default=None, min_length=1, max_length=100)
    max_jobs: Annotated[StrictInt, Field(ge=1, le=1000)] = 100
    request_key: RequestKey


class Run(StrictModel):
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class Stop(Run):
    request_key: RequestKey


class History(Page):
    filter: Literal["success", "failed", "canceled", "skipped", "audio", "media"] | None = None


class MediaInfo(StrictModel):
    path: str = Field(min_length=1, max_length=4096)
