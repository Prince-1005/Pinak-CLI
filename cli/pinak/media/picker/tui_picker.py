"""Interactive split-screen TUI media browser and picker."""

from __future__ import annotations

from pathlib import Path

from ...text_safety import safe_text
from ..core.input_parser import KeyEvent, MouseEvent
from ..visualizer.spectrum_bars import _fit_to_width, _visible_len
from .fuzzy_search import FuzzyMediaFilter
from .scanner import SUPPORTED_EXTENSIONS, MediaItem, MediaScanner


class TUIMediaPicker:
    """Renders a two-pane interactive media browser and captures user selection."""

    def __init__(self, start_dir: str | Path = ".") -> None:
        self.current_dir = Path(start_dir).resolve()
        if not self.current_dir.is_dir():
            self.current_dir = Path(".").resolve()

        self.all_items: list[MediaItem] = []
        self.visible_items: list[MediaItem] = []
        self.cursor_idx: int = 0
        self.search_query: str = ""
        self.is_searching: bool = False
        self.is_inputting_path: bool = False
        self.path_input: str = ""
        self.path_error: str = ""
        self._cursor_paths: dict[Path, Path] = {}
        self._cursor_positions: dict[Path, int] = {}
        self._refresh_directory()

    def _remember_cursor(self) -> None:
        if self.visible_items and 0 <= self.cursor_idx < len(self.visible_items):
            self._cursor_paths[self.current_dir] = self.visible_items[self.cursor_idx].path
            self._cursor_positions[self.current_dir] = self.cursor_idx

    def _refresh_directory(self, preferred_path: Path | None = None) -> None:
        """Rescan while restoring the last selected item in this directory."""
        self.all_items = MediaScanner.scan_directory(self.current_dir)
        self.visible_items = FuzzyMediaFilter.filter_items(self.all_items, self.search_query)
        wanted = preferred_path or self._cursor_paths.get(self.current_dir)
        if wanted is not None:
            for index, item in enumerate(self.visible_items):
                if item.path == wanted:
                    self.cursor_idx = index
                    break
            else:
                self.cursor_idx = min(
                    self._cursor_positions.get(self.current_dir, 0),
                    max(0, len(self.visible_items) - 1),
                )
        else:
            self.cursor_idx = 0

    def focus_path(self, path: Path) -> None:
        """Focus the file when returning from playback, including path-input selections."""
        if self.current_dir != path.parent:
            self._remember_cursor()
            self.current_dir = path.parent
            self.search_query = ""
        self._refresh_directory(preferred_path=path)
        if self.search_query and not any(item.path == path for item in self.visible_items):
            self.search_query = ""
            self._refresh_directory(preferred_path=path)

    def navigate_up(self) -> None:
        if self.visible_items:
            self.cursor_idx = (self.cursor_idx - 1) % len(self.visible_items)

    def navigate_down(self) -> None:
        if self.visible_items:
            self.cursor_idx = (self.cursor_idx + 1) % len(self.visible_items)

    def page_up(self) -> None:
        if self.visible_items:
            self.cursor_idx = max(0, self.cursor_idx - 10)

    def page_down(self) -> None:
        if self.visible_items:
            self.cursor_idx = min(len(self.visible_items) - 1, self.cursor_idx + 10)

    def ascend_directory(self) -> None:
        if self.current_dir.parent != self.current_dir:
            departed = self.current_dir
            self._remember_cursor()
            self.current_dir = self.current_dir.parent
            self.search_query = ""
            self._refresh_directory(preferred_path=departed)

    def select_current(self) -> Path | None:
        """
        Activates the currently selected row:
        - If directory: enters folder and returns None.
        - If file: returns confirmed Path for immediate playback.
        """
        if not self.visible_items or self.cursor_idx >= len(self.visible_items):
            return None

        selected = self.visible_items[self.cursor_idx]
        if selected.is_dir:
            if selected.path == self.current_dir.parent:
                self.ascend_directory()
                return None
            self._remember_cursor()
            self.current_dir = selected.path
            self.search_query = ""
            self._refresh_directory()
            return None

        return selected.path if selected.media_type else None

    def handle_input(self, event: KeyEvent | MouseEvent) -> tuple[bool, Path | None]:
        """
        Processes key/mouse event.
        Returns (should_re_render: bool, confirmed_file: Optional[Path]).
        """
        if isinstance(event, KeyEvent):
            k = " " if event.key == "space" else event.key
            if self.is_inputting_path:
                if k == "esc":
                    self.is_inputting_path = False
                    self.path_input = ""
                    self.path_error = ""
                    return True, None
                if k == "backspace":
                    if self.path_input:
                        self.path_input = self.path_input[:-1]
                    return True, None
                if k == "enter":
                    target_str = self.path_input.strip().strip("\"'")
                    if not target_str:
                        self.is_inputting_path = False
                        return True, None
                    target = Path(target_str).expanduser().resolve()
                    if target.is_dir():
                        self._remember_cursor()
                        self.current_dir = target
                        self.is_inputting_path = False
                        self.path_input = ""
                        self.path_error = ""
                        self.search_query = ""
                        self._refresh_directory()
                        return True, None
                    elif target.is_file() and target.suffix.lower() in SUPPORTED_EXTENSIONS:
                        self.is_inputting_path = False
                        return True, target
                    elif target.is_file():
                        self.path_error = "This file type cannot be opened"
                        return True, None
                    else:
                        self.path_error = f"Not found: {target_str[:25]}"
                        return True, None
                # Support single character typing and multi-character pasted text
                if k not in (
                    "up",
                    "down",
                    "pageup",
                    "pagedown",
                    "home",
                    "end",
                    "enter",
                    "esc",
                    "backspace",
                    "tab",
                ):
                    cleaned = k.replace("\r", "").replace("\n", "")
                    if cleaned:
                        self.path_input += cleaned
                        self.path_error = ""
                        return True, None
                return True, None

            if self.is_searching:
                if k == "esc":
                    self.is_searching = False
                    self.search_query = ""
                    self.visible_items = list(self.all_items)
                    self.cursor_idx = 0
                    return True, None
                if k == "enter":
                    self.is_searching = False
                    return True, None
                if k == "backspace":
                    if self.search_query:
                        self.search_query = self.search_query[:-1]
                        self.visible_items = FuzzyMediaFilter.filter_items(
                            self.all_items, self.search_query
                        )
                        self.cursor_idx = 0
                    return True, None
                if k == "up":
                    self.navigate_up()
                    return True, None
                if k == "down":
                    self.navigate_down()
                    return True, None
                if k == "pageup":
                    self.page_up()
                    return True, None
                if k == "pagedown":
                    self.page_down()
                    return True, None
                # Support typing and multi-character pasted text into search
                if k not in (
                    "up",
                    "down",
                    "pageup",
                    "pagedown",
                    "home",
                    "end",
                    "enter",
                    "esc",
                    "backspace",
                    "tab",
                ):
                    cleaned = k.replace("\r", "").replace("\n", "")
                    if cleaned:
                        self.search_query += cleaned
                        self.visible_items = FuzzyMediaFilter.filter_items(
                            self.all_items, self.search_query
                        )
                        self.cursor_idx = 0
                        return True, None
                return True, None

            if k == "up":
                self.navigate_up()
                return True, None
            if k == "down":
                self.navigate_down()
                return True, None
            if k == "pageup":
                self.page_up()
                return True, None
            if k == "pagedown":
                self.page_down()
                return True, None
            if k == "home":
                self.cursor_idx = 0
                return True, None
            if k == "end":
                self.cursor_idx = max(0, len(self.visible_items) - 1)
                return True, None
            if k == "enter":
                res = self.select_current()
                return True, res
            if k == "backspace":
                if self.search_query:
                    self.search_query = self.search_query[:-1]
                    self.visible_items = FuzzyMediaFilter.filter_items(
                        self.all_items, self.search_query
                    )
                    self.cursor_idx = 0
                    return True, None
                self.ascend_directory()
                return True, None
            if k in ("p", ":"):
                self.is_inputting_path = True
                self.path_input = ""
                self.path_error = ""
                return True, None
            if k == "/":
                self.is_searching = True
                return True, None
            if k == "esc":
                if self.search_query:
                    self.search_query = ""
                    self.visible_items = list(self.all_items)
                    self.cursor_idx = 0
                    return True, None
                return False, None
        elif isinstance(event, MouseEvent):
            if event.button == 64:  # Wheel Up
                self.navigate_up()
                return True, None
            if event.button == 65:  # Wheel Down
                self.navigate_down()
                return True, None

        return False, None

    def render_tui(self, cols: int, rows: int) -> str:
        """Renders the split-screen media browser TUI with modern high-contrast styling."""
        if self.is_inputting_path:
            prompt_lbl = " [📁 GOTO PATH]: "
            hint = " (Enter: Open, Esc: Cancel) "
            err_badge = f" \x1b[41;1;37m [!] {self.path_error} \x1b[0m" if self.path_error else ""
            v_err = _visible_len(err_badge)
            v_lbl = _visible_len(prompt_lbl)
            v_hint = _visible_len(hint)
            avail_box = max(10, cols - v_lbl - v_hint - v_err - 4)
            curr_text = safe_text(self.path_input) + "█"
            if len(curr_text) > avail_box:
                disp = curr_text[-avail_box:]
            else:
                disp = curr_text + (" " * (avail_box - len(curr_text)))
            box_rendered = f"\x1b[48;2;12;20;35m\x1b[38;2;255;255;255;1m[ {disp} ]\x1b[0m"
            raw_header = f"\x1b[48;2;24;42;72m\x1b[38;2;140;220;255;1m{prompt_lbl}\x1b[0m{box_rendered}{err_badge}\x1b[48;2;24;42;72m\x1b[38;2;200;220;240m{hint}\x1b[0m"
            header_bar = f"\x1b[2K{_fit_to_width(raw_header, cols)}"
        elif self.is_searching:
            prompt_lbl = " [🔍 SEARCH FILE NAME]: "
            hint = " (Enter: Done, Esc: Clear) "
            count_info = (
                f" \x1b[1;33m({len(self.visible_items)} match{'es' if len(self.visible_items) != 1 else ''})\x1b[0m"
                if self.search_query
                else ""
            )
            v_cnt = _visible_len(count_info)
            v_lbl = _visible_len(prompt_lbl)
            v_hint = _visible_len(hint)
            avail_box = max(10, cols - v_lbl - v_hint - v_cnt - 4)
            curr_text = safe_text(self.search_query) + "█"
            if len(curr_text) > avail_box:
                disp = curr_text[-avail_box:]
            else:
                disp = curr_text + (" " * (avail_box - len(curr_text)))
            box_rendered = f"\x1b[48;2;12;20;35m\x1b[38;2;255;255;255;1m[ {disp} ]\x1b[0m"
            raw_header = f"\x1b[48;2;28;48;80m\x1b[38;2;140;220;255;1m{prompt_lbl}\x1b[0m{box_rendered}{count_info}\x1b[48;2;28;48;80m\x1b[38;2;200;220;240m{hint}\x1b[0m"
            header_bar = f"\x1b[2K{_fit_to_width(raw_header, cols)}"
        else:
            path_str = safe_text(self.current_dir)
            if self.search_query:
                filter_text = f" 🔍 Filter: [{safe_text(self.search_query)}] [ ✕ Clear (Esc) ] "
            else:
                filter_text = " [ ✕ Close (Esc) ] "

            if cols >= 85:
                left_prefix = " 🔱 PINAK MEDIA PICKER │ 📂 Path: "
            elif cols >= 65:
                left_prefix = " 🔱 PINAK MEDIA PICKER │ 📂 "
            else:
                left_prefix = " 🔱 📂 "

            avail_for_path = max(
                4, cols - _visible_len(filter_text) - _visible_len(left_prefix) - 2
            )
            if len(path_str) > avail_for_path:
                path_disp = "..." + path_str[-(avail_for_path - 3) :]
            else:
                path_disp = path_str
            header_text = f"{left_prefix}{path_disp} "
            raw_header = f"\x1b[48;2;22;34;52m\x1b[38;2;120;225;255;1m{header_text}\x1b[0m"
            fit_left = cols - _visible_len(filter_text)
            header_bar = (
                f"\x1b[2K{_fit_to_width(raw_header, fit_left)}"
                f"\x1b[48;2;22;34;52m\x1b[38;2;120;225;255;1m{filter_text}\x1b[0m"
            )
            header_bar = _fit_to_width(header_bar, cols)

        # Responsive footer bar - fullscreen [f] option removed
        if cols >= 95:
            footer_text = " [↑/↓] Navigate  [Enter] Open  [p] Enter Path  [Backspace] Up  [/] Search  [Esc] Exit "
        elif cols >= 75:
            footer_text = " [↑/↓] Nav  [Enter] Open  [p] Path  [Bksp] Up  [/] Search  [Esc] Exit "
        elif cols >= 60:
            footer_text = " [↑/↓] Nav  [Enter] Open  [p] Path  [/] Search  [Esc] Exit "
        else:
            footer_text = " [↑/↓] Nav  [Enter] Open  [Esc] Exit "

        raw_footer = f"\x1b[48;2;28;34;46m\x1b[38;2;215;225;235m{footer_text}\x1b[0m"
        footer_bar = f"\x1b[2K{_fit_to_width(raw_footer, cols)}"

        content_rows = max(4, rows - 3)
        left_w = max(32, int(cols * 0.58))
        if cols >= 65 and (cols - left_w - 1) < 25:
            left_w = cols - 26
        right_w = max(20, cols - left_w - 1)

        # File list lines
        file_lines: list[str] = []
        scroll_start = max(
            0, min(self.cursor_idx - content_rows // 2, len(self.visible_items) - content_rows)
        )
        visible_slice = self.visible_items[scroll_start : scroll_start + content_rows]

        for idx, item in enumerate(visible_slice):
            actual_idx = scroll_start + idx
            is_cursor = actual_idx == self.cursor_idx
            pointer = " ▸ " if is_cursor else "   "
            badge_w = 8

            # Badges with distinct styling
            if item.is_dir:
                badge = "\x1b[1;33m📁 [DIR]\x1b[0m"
                cnt = item.child_media_count
                if cnt == 1:
                    size_styled = "\x1b[1;33m1 file\x1b[0m"
                    size_clean = "1 file"
                elif cnt > 0:
                    size_styled = f"\x1b[1;33m{cnt} files\x1b[0m"
                    size_clean = f"{cnt} files"
                else:
                    size_styled = "\x1b[38;2;130;140;155m0 files\x1b[0m"
                    size_clean = "0 files"
            elif item.media_type == "video":
                badge = "\x1b[1;36m🎬 [VID]\x1b[0m"
                mb = item.size_bytes / (1024 * 1024)
                size_styled = f"{mb:.1f}MB"
                size_clean = size_styled
            elif item.media_type == "audio":
                badge = "\x1b[1;35m🎵 [AUD]\x1b[0m"
                mb = item.size_bytes / (1024 * 1024)
                size_styled = f"{mb:.1f}MB"
                size_clean = size_styled
            elif item.media_type == "picture":
                badge = "\x1b[1;32m🖼 [PIC]\x1b[0m"
                mb = item.size_bytes / (1024 * 1024)
                size_styled = f"{mb:.1f}MB"
                size_clean = size_styled
            else:
                badge = "\x1b[38;2;150;155;165m📄 [FILE]\x1b[0m"
                mb = item.size_bytes / (1024 * 1024)
                size_styled = f"{mb:.1f}MB"
                size_clean = size_styled

            size_w = 9
            size_pad = max(0, size_w - len(size_clean))
            size_col = (" " * size_pad) + size_styled

            name_w = max(8, left_w - 3 - badge_w - 1 - size_w - 1)
            name_col = _fit_to_width(item.name, name_w)

            row_core = f"{pointer}{badge} {name_col} {size_col}"
            row_fitted = _fit_to_width(row_core, left_w)

            row_str = f"\x1b[48;2;36;55;92m\x1b[1m{row_fitted}\x1b[0m" if is_cursor else row_fitted

            file_lines.append(row_str)

        while len(file_lines) < content_rows:
            file_lines.append(" " * left_w)

        # Right pane: Media Inspector card with box borders
        right_lines: list[str] = []
        box_w = max(18, min(right_w - 2, 54))
        inner_w = box_w - 2

        def _box_row(content: str) -> str:
            fitted = _fit_to_width(content, inner_w)
            return f" \x1b[38;2;70;95;135m│\x1b[0m{fitted}\x1b[38;2;70;95;135m│\x1b[0m"

        right_lines.append(f" \x1b[38;2;70;95;135m╭{'─' * inner_w}╮\x1b[0m")
        right_lines.append(_box_row(" \x1b[1;36m✦ MEDIA INSPECTOR\x1b[0m"))
        right_lines.append(f" \x1b[38;2;70;95;135m├{'─' * inner_w}┤\x1b[0m")

        if self.visible_items and self.cursor_idx < len(self.visible_items):
            cur = self.visible_items[self.cursor_idx]
            right_lines.append(_box_row(f" Name: {cur.name}"))
            if cur.is_dir:
                type_lbl = "DIRECTORY"
            elif cur.media_type:
                type_lbl = cur.media_type.upper()
            else:
                type_lbl = "UNSUPPORTED FILE"
            right_lines.append(_box_row(f" Type: {type_lbl}"))
            if cur.is_dir:
                cnt = cur.child_media_count
                right_lines.append(_box_row(f" Total: {cnt} media file{'s' if cnt != 1 else ''}"))
                right_lines.append(_box_row(""))
                right_lines.append(_box_row(" \x1b[1;33m▶ Press [Enter] to Open Folder\x1b[0m"))
            else:
                sz_mb = cur.size_bytes / (1024 * 1024)
                right_lines.append(_box_row(f" Size: {sz_mb:.2f} MB"))
                right_lines.append(_box_row(f" Ext:  {cur.path.suffix.upper()}"))
                right_lines.append(_box_row(""))
                if cur.media_type:
                    right_lines.append(_box_row(" \x1b[1;32m▶ Press [Enter] to Open\x1b[0m"))
                else:
                    right_lines.append(
                        _box_row(" \x1b[1;33mThis file type cannot be opened\x1b[0m")
                    )
        else:
            right_lines.append(_box_row(" No item selected"))

        right_lines.append(f" \x1b[38;2;70;95;135m╰{'─' * inner_w}╯\x1b[0m")

        # Pad right_lines and strictly enforce right_w
        fitted_right_lines: list[str] = []
        for r in range(content_rows):
            line = right_lines[r] if r < len(right_lines) else ""
            fitted_right_lines.append(_fit_to_width(line, right_w))

        # Combine left and right panes with clean divider
        divider = "\x1b[38;2;70;85;110m│\x1b[0m"
        body_lines: list[str] = []
        for r in range(content_rows):
            left_part = file_lines[r]
            right_part = fitted_right_lines[r]
            body_lines.append(f"{left_part}{divider}{right_part}")

        return f"{header_bar}\n" + "\n".join(body_lines) + f"\n{footer_bar}"
