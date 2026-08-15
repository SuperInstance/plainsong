"""Tests for the terminal interface without requiring a real terminal."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tapscript.interfaces.tui import (
    HELP,
    TuiState,
    _init_colours,
    _pair,
    _safe_add,
    check_importable,
)
from tapscript.library import LibraryEntry
from tapscript.runtime.config import load_config
from tapscript.runtime.paths import Paths

MINIMAL_NOTATION = """**TRACK: Test Piece**
[MetaData]
key: C | tempo: 100 | meter: 4/4

[Section]
Melody: | C4 D4 E4 F4 |
"""

MALFORMED_NOTATION = """This is not valid notation at all.
There's no structure, no metadata, nothing.
"""


class TestCheckImportable(unittest.TestCase):
    """The spec check that curses is available."""

    def test_returns_a_pair(self):
        """check_importable returns (bool, str)."""
        result = check_importable()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], bool)
        self.assertIsInstance(result[1], str)

    def test_reports_accurately_whether_curses_is_there(self):
        """The report must match reality, which is platform-dependent.

        Stock Python on Windows ships no curses module -- it needs the
        windows-curses package -- so this cannot assert availability. What it
        can assert is that the answer agrees with whether the import works,
        because a spec check that lies is worse than one that reports a
        missing capability.
        """
        try:
            import curses  # noqa: F401

            available = True
        except ImportError:
            available = False

        ok, message = check_importable()
        self.assertEqual(ok, available)
        self.assertIn("curses", message.lower())


class TestHelpStructure(unittest.TestCase):
    """Validate that HELP is well-formed."""

    def test_help_is_a_list(self):
        """HELP is a list."""
        self.assertIsInstance(HELP, list)

    def test_every_help_entry_is_a_pair(self):
        """Every entry in HELP is a pair (key, description)."""
        self.assertGreater(len(HELP), 0)
        for entry in HELP:
            self.assertIsInstance(entry, tuple)
            self.assertEqual(len(entry), 2)

    def test_every_help_entry_has_non_empty_strings(self):
        """Both key and description are non-empty strings."""
        for key, description in HELP:
            self.assertIsInstance(key, str)
            self.assertIsInstance(description, str)
            self.assertGreater(len(key), 0)
            self.assertGreater(len(description), 0)

    def test_help_covers_major_commands(self):
        """HELP mentions key commands like quit and help."""
        keys = [key for key, _desc in HELP]
        self.assertIn("q", keys)
        self.assertIn("?", keys)


class TestTuiStateConstruction(unittest.TestCase):
    """TuiState initializes correctly."""

    def setUp(self):
        self.config = load_config()

    def test_construction_succeeds(self):
        """TuiState can be constructed with a Config."""
        state = TuiState(self.config)
        self.assertIsNotNone(state)

    def test_has_library(self):
        """TuiState builds a Library."""
        state = TuiState(self.config)
        self.assertIsNotNone(state.library)

    def test_has_entries(self):
        """TuiState populates entries from the library."""
        state = TuiState(self.config)
        self.assertIsInstance(state.entries, list)
        # The real library has thousands of entries
        self.assertGreater(len(state.entries), 0)

    def test_initial_state_values(self):
        """TuiState initializes with correct default values."""
        state = TuiState(self.config)
        self.assertEqual(state.filter, "")
        self.assertEqual(state.selected, 0)
        self.assertEqual(state.offset, 0)
        self.assertEqual(state.status, "ready")
        self.assertFalse(state.busy)
        self.assertEqual(state.detail, {})
        self.assertEqual(state.preview, [])
        self.assertEqual(state.message_lines, [])


class TestTuiStateVisible(unittest.TestCase):
    """TuiState.visible() returns filtered entries."""

    def setUp(self):
        self.config = load_config()
        self.state = TuiState(self.config)

    def test_visible_without_filter_returns_all_entries(self):
        """With no filter, visible() returns all entries."""
        all_entries = self.state.entries
        visible = self.state.visible()
        self.assertEqual(visible, all_entries)

    def test_visible_with_filter_searches(self):
        """With a filter, visible() returns search results."""
        self.state.filter = "c"
        visible = self.state.visible()
        # Should return a subset (search results)
        self.assertIsInstance(visible, list)
        # The search will find pieces matching "c"
        self.assertGreater(len(visible), 0)

    def test_visible_with_nonmatching_filter_returns_empty(self):
        """A filter that matches nothing returns empty list."""
        self.state.filter = "zzz_no_notation_has_this_string_in_it_zzz"
        visible = self.state.visible()
        self.assertEqual(visible, [])


class TestTuiStateCurrent(unittest.TestCase):
    """TuiState.current() returns the selected entry."""

    def setUp(self):
        self.config = load_config()
        self.state = TuiState(self.config)

    def test_current_returns_selected_entry(self):
        """current() returns the entry at the selected index."""
        self.state.selected = 0
        current = self.state.current()
        self.assertIsNotNone(current)
        self.assertIsInstance(current, LibraryEntry)

    def test_current_handles_out_of_range_selection(self):
        """When selected > len(visible), current() returns the last entry."""
        visible = self.state.visible()
        self.state.selected = 999999  # Way out of range
        current = self.state.current()
        self.assertEqual(current, visible[-1])

    def test_current_respects_filter(self):
        """current() returns from the filtered list when filter is set."""
        # Set a filter that matches at least 2 entries
        self.state.filter = "a"
        visible = self.state.visible()
        if len(visible) >= 2:
            self.state.selected = 1
            current = self.state.current()
            # Should be the second item in the filtered list
            self.assertEqual(current, visible[1])

    def test_current_returns_none_for_empty_library(self):
        """When visible() is empty, current() returns None."""
        # Use a filter that matches nothing
        self.state.filter = "zzz_impossible_filter_zzz"
        current = self.state.current()
        self.assertIsNone(current)


class TestTuiStateLoadCurrent(unittest.TestCase):
    """TuiState.load_current() loads and parses the selected entry."""

    def setUp(self):
        self.config = load_config()
        self.state = TuiState(self.config)
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_current_on_empty_library(self):
        """load_current() handles empty library gracefully."""
        self.state.filter = "zzz_impossible_filter_zzz"
        initial_status = self.state.status
        self.state.load_current()
        # Should return without error, status unchanged
        self.assertEqual(self.state.status, initial_status)
        self.assertEqual(self.state.preview, [])
        self.assertEqual(self.state.detail, {})

    def test_load_current_populates_preview_and_detail(self):
        """load_current() on a valid entry populates preview and detail."""
        # Create a temporary valid notation file
        tap_file = Path(self.temp_dir.name) / "test.tap"
        tap_file.write_text(MINIMAL_NOTATION, encoding="utf-8")

        # Create a library entry pointing to it
        entry = LibraryEntry(
            path=tap_file,
            name="test",
            title="Test Piece",
            key="C",
            tempo=100,
        )

        # Manually set current entry by replacing visible
        self.state.entries = [entry]
        self.state.selected = 0

        self.state.load_current()

        # Should have populated preview
        self.assertGreater(len(self.state.preview), 0)
        # Should have populated detail
        self.assertGreater(len(self.state.detail), 0)
        self.assertIn("title", self.state.detail)
        self.assertIn("key", self.state.detail)
        # Status should reflect successful load
        self.assertIn("test", self.state.status.lower())

    def test_load_current_truncates_long_files(self):
        """load_current() truncates preview to 400 lines."""
        # Create a file with 500 lines
        tap_file = Path(self.temp_dir.name) / "long.tap"
        lines = ["line content"] * 500
        tap_file.write_text("\n".join(lines), encoding="utf-8")

        entry = LibraryEntry(path=tap_file, name="long", title="Long File")
        self.state.entries = [entry]
        self.state.selected = 0

        self.state.load_current()

        # Preview should be at most 400 lines
        self.assertLessEqual(len(self.state.preview), 400)

    def test_load_current_on_unreadable_file_sets_status(self):
        """load_current() on an unreadable file sets status, doesn't raise."""
        # Create a mock entry that raises OSError on read()
        entry = mock.Mock(spec=LibraryEntry)
        entry.name = "unreadable"
        entry.read.side_effect = OSError("Permission denied")

        self.state.entries = [entry]
        self.state.selected = 0

        # Should not raise
        self.state.load_current()

        # Should set status to report the error
        self.assertIn("could not read", self.state.status)
        self.assertIn("unreadable", self.state.status)
        # detail and preview should be empty
        self.assertEqual(self.state.detail, {})
        self.assertEqual(self.state.preview, [])

    def test_load_current_on_malformed_notation_still_loads_gracefully(self):
        """load_current() on malformed notation handles it gracefully, doesn't raise."""
        tap_file = Path(self.temp_dir.name) / "malformed.tap"
        tap_file.write_text(MALFORMED_NOTATION, encoding="utf-8")

        entry = LibraryEntry(path=tap_file, name="malformed", title="Malformed")
        self.state.entries = [entry]
        self.state.selected = 0

        # Should not raise, even with malformed input
        self.state.load_current()

        # Parser is lenient and returns a structure even for malformed input
        # Just verify it has a status set
        self.assertIsInstance(self.state.status, str)
        self.assertGreater(len(self.state.status), 0)
        # Should have populated preview from the file content
        self.assertGreater(len(self.state.preview), 0)


class TestSafeAdd(unittest.TestCase):
    """_safe_add() handles bounds and exceptions safely."""

    def test_safe_add_with_valid_position(self):
        """_safe_add() writes text to a valid position."""
        # Create a minimal fake screen
        screen = mock.Mock()
        screen.getmaxyx.return_value = (24, 80)  # height, width

        _safe_add(screen, 5, 10, "hello", attr=0)

        # Should have called addnstr
        screen.addnstr.assert_called_once()
        call_args = screen.addnstr.call_args
        self.assertEqual(call_args[0][0], 5)  # row
        self.assertEqual(call_args[0][1], 10)  # column
        self.assertEqual(call_args[0][2], "hello")  # text

    def test_safe_add_with_row_out_of_bounds(self):
        """_safe_add() skips drawing when row is out of bounds."""
        screen = mock.Mock()
        screen.getmaxyx.return_value = (24, 80)

        # Row above screen
        _safe_add(screen, -1, 10, "hello")
        screen.addnstr.assert_not_called()

        # Row below screen
        screen.reset_mock()
        _safe_add(screen, 24, 10, "hello")
        screen.addnstr.assert_not_called()

    def test_safe_add_with_no_available_space(self):
        """_safe_add() skips drawing when there's no space."""
        screen = mock.Mock()
        screen.getmaxyx.return_value = (24, 80)

        # Column at the end with no space
        _safe_add(screen, 5, 79, "hello")
        screen.addnstr.assert_not_called()

    def test_safe_add_swallows_exceptions(self):
        """_safe_add() swallows exceptions from addnstr."""
        screen = mock.Mock()
        screen.getmaxyx.return_value = (24, 80)
        screen.addnstr.side_effect = Exception("Curses error")

        # Should not raise
        _safe_add(screen, 5, 10, "hello")

    def test_safe_add_with_attribute(self):
        """_safe_add() passes the attribute to addnstr."""
        screen = mock.Mock()
        screen.getmaxyx.return_value = (24, 80)

        attr_value = 42
        _safe_add(screen, 5, 10, "text", attr=attr_value)

        screen.addnstr.assert_called_once()
        call_args = screen.addnstr.call_args
        # addnstr is called as: (row, column, text, available, attr)
        self.assertEqual(call_args[0][4], attr_value)  # The attr parameter (5th positional arg)

    def test_safe_add_clips_text_to_available_space(self):
        """_safe_add() limits text length to available space."""
        screen = mock.Mock()
        screen.getmaxyx.return_value = (24, 80)

        # Starting at column 75, should have 4 chars available (80-75-1)
        _safe_add(screen, 5, 75, "hello world")

        screen.addnstr.assert_called_once()
        call_args = screen.addnstr.call_args
        # The second element should be the max length
        max_length = call_args[0][3]  # third positional arg after row, col, text
        self.assertLessEqual(max_length, 4)


class TestPair(unittest.TestCase):
    """_pair() returns color pair or 0 based on curses availability."""

    def test_pair_with_colors_available(self):
        """When curses.has_colors() is True, return color_pair()."""
        import sys

        mock_curses = mock.Mock()
        mock_curses.has_colors.return_value = True
        mock_curses.color_pair.return_value = 8

        with mock.patch.dict(sys.modules, {"curses": mock_curses}):
            result = _pair(1)

            mock_curses.color_pair.assert_called_once_with(1)
            self.assertEqual(result, 8)

    def test_pair_without_colors(self):
        """When curses.has_colors() is False, return 0."""
        import sys

        mock_curses = mock.Mock()
        mock_curses.has_colors.return_value = False

        with mock.patch.dict(sys.modules, {"curses": mock_curses}):
            result = _pair(1)

            self.assertEqual(result, 0)


class TestInitColours(unittest.TestCase):
    """_init_colours() initializes color pairs safely."""

    def test_init_colours_with_colors_available(self):
        """When curses.has_colors() is True, init_pair is called."""
        import sys

        mock_curses = mock.Mock()
        mock_curses.has_colors.return_value = True

        with mock.patch.dict(sys.modules, {"curses": mock_curses}):
            _init_colours()

            # Should have called the color initialization functions
            mock_curses.start_color.assert_called_once()
            mock_curses.use_default_colors.assert_called_once()
            # Should have called init_pair for each color pair
            self.assertGreater(mock_curses.init_pair.call_count, 0)

    def test_init_colours_without_colors(self):
        """When curses.has_colors() is False, nothing happens."""
        import sys

        mock_curses = mock.Mock()
        mock_curses.has_colors.return_value = False

        with mock.patch.dict(sys.modules, {"curses": mock_curses}):
            _init_colours()

            # Should have returned early without calling color functions
            mock_curses.start_color.assert_not_called()
            mock_curses.use_default_colors.assert_not_called()
            mock_curses.init_pair.assert_not_called()


class TestTuiStateIntegration(unittest.TestCase):
    """Integration tests for TuiState with real and fake data."""

    def setUp(self):
        self.config = load_config()

    def test_filter_then_select_then_load(self):
        """Workflow: filter library, select entry, load it."""
        state = TuiState(self.config)

        # Filter to a specific piece
        state.filter = "a"
        visible = state.visible()
        self.assertGreater(len(visible), 0)

        # Select first result
        state.selected = 0
        current = state.current()
        self.assertIsNotNone(current)

        # Load it (should work for real files in library)
        state.load_current()
        # Just verify it doesn't crash; preview/detail depend on file validity

    def test_selection_bounds_during_navigation(self):
        """current() bounds selection even if selected is out of range."""
        state = TuiState(self.config)
        visible = state.visible()

        # Set selected way out of range
        state.selected = 999999

        # current() should still return the last entry
        current = state.current()
        self.assertEqual(current, visible[-1])

    def test_library_with_custom_paths(self):
        """TuiState can use a custom library root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a minimal library structure
            root = Path(tmpdir)
            lib_dir = root / "library"
            lib_dir.mkdir()

            tap_file = lib_dir / "test.tap"
            tap_file.write_text(MINIMAL_NOTATION)

            # Create a Paths object pointing to the temp directory
            paths = Paths(project_root=root)

            # Mock the config to use our paths
            config = load_config()
            config.paths = paths

            # Create state
            state = TuiState(config)

            # The library should find our test file
            # (This depends on implementation details of Library refresh)
            self.assertIsNotNone(state.library)


if __name__ == "__main__":
    unittest.main()
