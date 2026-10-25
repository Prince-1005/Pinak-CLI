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


class HistoryShow(Page):
    history_id: PositiveID


class LibraryScan(StrictModel):
    folder: str = Field(min_length=1, max_length=4096)


class LibraryList(Page):
    media_type: Literal["audio", "video", "picture"] | None = None


class LibrarySearch(Page):
    query: str = Field(default="", max_length=256)
    tag: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def term(self) -> LibrarySearch:
        if not self.query.strip() and not (self.tag or "").strip():
            raise ValueError("Give a query or tag")
        return self


class LibraryRef(StrictModel):
    media_id: PositiveID


class LibraryStorage(Page):
    root: str | None = Field(default=None, min_length=1, max_length=4096)
    collection_id: PositiveID | None = None
    root_cursor: Annotated[StrictInt, Field(ge=0)] = 0
    collection_cursor: Annotated[StrictInt, Field(ge=0)] = 0


class LibraryEdit(LibraryRef):
    request_key: RequestKey


class LibraryTag(LibraryEdit):
    name: str = Field(min_length=1, max_length=100)


class LibraryRelink(LibraryEdit):
    path: str = Field(min_length=1, max_length=4096)


class CollectionCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    request_key: RequestKey


class CollectionRef(StrictModel):
    collection_id: PositiveID


class CollectionPage(Page):
    pass


class CollectionShow(CollectionRef):
    cursor: PositiveID | None = None
    limit: Annotated[StrictInt, Field(ge=1, le=100)] = 25


class CollectionEdit(CollectionRef):
    media_id: PositiveID
    request_key: RequestKey


class CollectionMove(CollectionEdit):
    before_id: PositiveID


class BookmarkAdd(LibraryEdit):
    seconds: float = Field(ge=0, allow_inf_nan=False)
    note: str = Field(default="", max_length=500)


class BookmarkRef(StrictModel):
    bookmark_id: PositiveID


class BookmarkPage(LibraryRef):
    cursor: PositiveID | None = None
    limit: Annotated[StrictInt, Field(ge=1, le=100)] = 25


class BookmarkRemove(BookmarkRef):
    request_key: RequestKey


class MediaInfo(StrictModel):
    path: str = Field(min_length=1, max_length=4096)
