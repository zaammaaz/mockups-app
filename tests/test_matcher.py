from pathlib import Path

import matcher


def test_picks_by_orientation_keyword():
    assert matcher.pick_oriented_file(Path("X_horizontal.psd"), "v", "h", "s") == "h"
    assert matcher.pick_oriented_file(Path("X_vertical.psd"), "v", "h", "s") == "v"
    assert matcher.pick_oriented_file(Path("X_square.psd"), "v", "h", "s") == "s"


def test_missing_file_for_orientation_returns_none():
    assert matcher.pick_oriented_file(Path("X_vertical.psd"), "", "h", "s") is None


def test_no_orientation_keyword_returns_none():
    assert matcher.pick_oriented_file(Path("X_plain.psd"), "v", "h", "s") is None


def test_square_takes_precedence():
    assert matcher.pick_oriented_file(Path("X_square_horizontal.psd"), "v", "h", "s") == "s"
