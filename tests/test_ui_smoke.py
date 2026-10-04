from pathlib import Path

import main


def _app():
    app = main.MockupGeneratorApp()
    app.withdraw()
    return app


def test_app_constructs_and_switches_mode():
    app = _app()
    assert app._mode == main.MODE_LOGO
    assert app._mode_cards[main.MODE_LOGO].winfo_manager() == "grid"
    assert app._mode_cards[main.MODE_VIDEO].winfo_manager() == ""
    app._select_mode(main.MODE_VIDEO)
    assert app._mode == main.MODE_VIDEO
    assert app._mode_cards[main.MODE_VIDEO].winfo_manager() == "grid"
    assert app._mode_cards[main.MODE_LOGO].winfo_manager() == ""
    app.destroy()


def test_duration_clamp_pure():
    app = _app()
    app._video_duration_var.set("999"); assert app._get_duration() == 60
    app._video_duration_var.set("abc"); assert app._get_duration() == 10
    app._video_duration_var.set("5"); assert app._get_duration() == 5
    assert app._video_duration_var.get() == "5"  # pure: field unchanged
    app.destroy()


def test_build_job_list_orientations():
    app = _app()
    mixed = [Path(r"C:\t\P_vertical.psd"), Path(r"C:\t\P_horizontal.psd"),
             Path(r"C:\t\P_square.psd"), Path(r"C:\t\P_plain.psd")]

    # Artwork: only vertical provided -> only the *vertical* template, rest skipped
    app._select_mode(main.MODE_ARTWORK)
    app._vertical_artwork_var.set("v.png")
    app._matches = {"P": mixed}
    jobs, skipped = app._build_job_list()
    assert len(jobs) == 1 and jobs[0]["image_path"] == "v.png"
    assert "vertical" in jobs[0]["psd_path"].name.lower()
    assert len(skipped) == 3

    # Video: horizontal + square provided -> two jobs, correct files + duration
    app._select_mode(main.MODE_VIDEO)
    app._horizontal_video_var.set("h.mp4")
    app._square_video_var.set("s.mp4")
    app._video_duration_var.set("8")
    app._matches = {"P": mixed}
    vjobs, _ = app._build_job_list()
    assert sorted(j["video_path"] for j in vjobs) == ["h.mp4", "s.mp4"]
    assert all(j["duration"] == 8 for j in vjobs)

    # Logo unaffected (regression)
    app._select_mode(main.MODE_LOGO)
    app._logo_path_var.set(r"C:\fake\logo.png"); app._bg_color_var.set("#FFFFFF")
    app._matches = {"P": [Path(r"C:\fake\P.psd")]}
    ljobs, _ = app._build_job_list()
    assert len(ljobs) == 1 and "image_path" in ljobs[0]
    app.destroy()


def test_child_cmd_dev_includes_script():
    app = _app()
    cmd = app._child_cmd("--ps-probe")
    assert cmd[0] == main.sys.executable
    assert cmd[-1] == "--ps-probe"
    assert any(c.endswith("main.py") for c in cmd)  # dev: re-runs the script
    app.destroy()


def test_ps_probe_timeout_is_handled(monkeypatch):
    # A hung Photoshop -> child killed on timeout -> clear message, no freeze.
    def boom(*a, **k):
        raise main.subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(main.subprocess, "run", boom)
    app = _app()
    ok, msg = app._ps_probe(1)
    assert ok is False
    assert "document" in msg.lower() or "not answering" in msg.lower()
    app.destroy()


def test_ps_run_job_timeout_is_handled(monkeypatch):
    def boom(*a, **k):
        raise main.subprocess.TimeoutExpired(cmd="x", timeout=1)
    monkeypatch.setattr(main.subprocess, "run", boom)
    app = _app()
    ok, err = app._ps_run_job({"mode": "logo"}, 1)
    assert ok is False and "timed out" in err.lower()
    app.destroy()


def test_ps_run_job_success(monkeypatch):
    class _R:
        returncode = 0
        stderr = ""
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: _R())
    app = _app()
    ok, err = app._ps_run_job({"mode": "logo"}, 5)
    assert ok is True and err == ""
    app.destroy()


def test_clear_log_empties_textbox():
    app = _app()
    app._log_textbox.configure(state="normal")
    app._log_textbox.insert("end", "hello\nworld\n")
    app._log_textbox.configure(state="disabled")
    assert app._log_textbox.get("1.0", "end").strip() != ""
    app._clear_log()
    assert app._log_textbox.get("1.0", "end").strip() == ""
    app.destroy()
