"""Seeds the playlist manager with sibling media files from the same folder."""

from __future__ import annotations

from pathlib import Path

from .scanner import MediaScanner


class SiblingPlaylistSeeder:
    """Discovers sibling media files in parent folder to populate the active playlist."""

    @classmethod
    def seed_from_file(cls, selected_file: str | Path) -> tuple[list[Path], int]:
        target = Path(selected_file).resolve()
        if not target.is_file():
            return [target], 0

        parent_dir = target.parent
        items = MediaScanner.scan_directory(parent_dir)

        # Classify target media type
        target_ext = target.suffix.lower()
        from .scanner import SUPPORTED_EXTENSIONS

        target_type = SUPPORTED_EXTENSIONS.get(target_ext)

        # Filter out directories and match target media type if identified
        if target_type:
            sibling_paths: list[Path] = [
                it.path for it in items if not it.is_dir and it.media_type == target_type
            ]
        else:
            sibling_paths = [it.path for it in items if not it.is_dir]

        if not sibling_paths:
            return [target], 0

        try:
            start_idx = sibling_paths.index(target)
        except ValueError:
            sibling_paths.insert(0, target)
            start_idx = 0

        return sibling_paths, start_idx
