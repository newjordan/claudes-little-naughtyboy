"""Popup construction. Display tests skip when Tk cannot open."""

from __future__ import annotations

from pathlib import Path

import pytest

POPUP_TEXT = "ah ah ah, your not allowed to do that"


def _tk_root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tkinter display is not available: {exc}")
    root.withdraw()
    return root


def _is_destroyed(root) -> bool:
    try:
        return not root.winfo_exists()
    except Exception:
        return True


def test_animation_sequence_wags_three_frames(hook):
    assert hook.animation_sequence(3) == [0, 1, 2, 1]
    assert hook.animation_sequence(1) == [0]
    assert hook.animation_sequence(0) == []


def test_default_frames_resolve_to_the_three_poses(hook):
    paths = hook.resolve_frame_paths()
    assert [path.name for path in paths] == [
        "dario-lockout-frame-1.png",
        "dario-lockout-frame-2.png",
        "dario-lockout-frame-3.png",
    ]
    assert all(path.is_file() for path in paths)


def test_missing_pose_falls_back_to_the_single_image(hook, monkeypatch):
    monkeypatch.setattr(hook, "DEFAULT_FRAME_PATHS", [Path("/missing/frame.png")])
    monkeypatch.delenv("AH_AH_AH_IMAGE", raising=False)
    assert hook.resolve_frame_paths() == [hook.DEFAULT_IMAGE_PATH]


def test_explicit_frame_list_uses_the_path_separator(hook, monkeypatch, tmp_path):
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    monkeypatch.setenv("AH_AH_AH_FRAMES", f"{first}{hook.os.pathsep}{second}")
    assert hook.resolve_frame_paths() == [first, second]


def test_popup_text_is_the_exact_lockout_line(hook):
    assert hook.POPUP_TEXT == POPUP_TEXT


def test_dialog_closes_from_the_titlebar_and_names_the_event(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_POPUP_REASON", "MessageDisplay")
    monkeypatch.setenv("AH_AH_AH_FRAME_MS", "0")
    root = _tk_root()
    try:
        ui = hook.create_popup(root)
        assert ui["message"].cget("text") == POPUP_TEXT
        assert ui["caption"].cget("text") == "Detected on MessageDisplay"
        assert ui["sequence"] == [0, 1, 2, 1]
        assert len(ui["frames"]) == 3
        assert root.bind("<Escape>")
        ui["close"].invoke()
        assert _is_destroyed(root)
    finally:
        if not _is_destroyed(root):
            root.destroy()


def test_ok_closes_and_manual_test_caption_is_plain(hook, monkeypatch):
    monkeypatch.setenv("AH_AH_AH_POPUP_REASON", "manual test")
    monkeypatch.setenv("AH_AH_AH_FRAME_MS", "0")
    root = _tk_root()
    try:
        ui = hook.create_popup(root)
        assert ui["caption"].cget("text") == "Manual test"
        ui["ok"].invoke()
        assert _is_destroyed(root)
    finally:
        if not _is_destroyed(root):
            root.destroy()


def test_frames_scale_inside_the_max_side(hook):
    pytest.importorskip("PIL")
    root = _tk_root()
    try:
        frames = hook._load_photo_frames(root, hook.DEFAULT_FRAME_PATHS, 120)
        assert len(frames) == 3
        assert all(0 < frame.width() <= 120 for frame in frames)
        assert all(0 < frame.height() <= 120 for frame in frames)
    finally:
        root.destroy()


def test_missing_image_does_not_raise(hook, tmp_path):
    root = _tk_root()
    try:
        frames = hook._load_photo_frames(root, [tmp_path / "missing.png"], 40)
        assert frames == []
    finally:
        root.destroy()


def test_foreground_test_flag_reports_a_missing_tkinter(hook, monkeypatch, capsys):
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "tkinter" or name.startswith("tkinter."):
            raise ModuleNotFoundError("tkinter")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert hook.main(["--test"]) == 1
    captured = capsys.readouterr()
    assert "Tkinter" in captured.err
    assert captured.out == ""
