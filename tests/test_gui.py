"""Drives the real Tk interface programmatically (no mouse/keyboard needed)."""

import time
import tkinter as tk
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def tk_root():
    # one Tk interpreter per process: creating and destroying several is unreliable on Windows
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(monkeypatch, tmp_path, tk_root):
    from osumapgen import gui, infra
    monkeypatch.setattr(infra, "app_data_dir", lambda: tmp_path)      # don't touch real settings
    monkeypatch.setattr(gui.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *a, **k: None)   # skip first-run prompt
    win = tk.Toplevel(tk_root)
    win.withdraw()
    a = gui.App(win)
    yield a
    win.destroy()


def run_until_done(app, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        app.root.update()
        if app.worker is not None and not app.worker.is_alive() and str(app.gen_btn["state"]) == "normal":
            app.root.update()
            return
        time.sleep(0.05)
    raise AssertionError("GUI generation did not finish")


def test_generate_through_gui(app, song, tmp_path):
    p, _ = song("short")
    app.mp3_var.set(str(p))
    app.stars_var.set("3.5")
    app.style_var.set("Auto")
    app.out_var.set(str(tmp_path / "gui_out"))
    app.generate()
    run_until_done(app)
    res = app.result
    assert res is not None and res.ok, res and res.errors
    assert Path(res.osz_path).is_file()
    assert "Requested: 3.50" in app.stars_info.get()
    assert str(app.open_folder_btn["state"]) == "normal"
    assert str(app.open_osu_btn["state"]) == "normal"
    # settings were remembered
    from osumapgen.infra import Settings
    s = Settings.load()
    assert s.stars == 3.5 and s.last_mp3 == str(p)


def test_gui_cancel(app, song, tmp_path):
    p, _ = song("full")
    app.mp3_var.set(str(p))
    app.stars_var.set("4")
    app.out_var.set(str(tmp_path / "gui_cancel"))
    app.generate()
    app.cancel()
    run_until_done(app)
    assert app.result is None
    assert "Cancel" in app.status.get()


def test_gui_rejects_bad_input(app):
    app.mp3_var.set("")
    app.generate()
    assert app.worker is None


def test_username_is_written_as_creator_and_remembered(app, song, tmp_path):
    p, _ = song("short")
    app.mp3_var.set(str(p))
    app.stars_var.set("3")
    app.user_var.set("Some_Player")
    app.out_var.set(str(tmp_path / "gui_user"))
    app.generate()
    run_until_done(app)
    assert app.result.ok
    text = Path(app.result.osu_path).read_text(encoding="utf-8")
    assert "Creator:Some_Player" in text           # case preserved exactly
    assert "(Some_Player)" in Path(app.result.osu_path).name
    from osumapgen.infra import Settings
    assert Settings.load().username == "Some_Player"


def test_invalid_username_blocks_generation(app, song, monkeypatch):
    from osumapgen import gui
    shown = []
    monkeypatch.setattr(gui.messagebox, "showwarning", lambda *a, **k: shown.append(a))
    p, _ = song("short")
    app.mp3_var.set(str(p))
    app.user_var.set("bad@name!")
    app.generate()
    assert app.worker is None
    assert shown and "CASE-SENSITIVE" not in shown[0][1] and "Case-sensitive" in shown[0][1]


def test_first_run_prompt_saves_username(app, monkeypatch):
    from osumapgen import gui
    answers = iter(["x", "Cool Mapper"])                 # first too short, then valid
    monkeypatch.setattr(gui.simpledialog, "askstring", lambda *a, **k: next(answers))
    app.settings.username_asked = False
    app.ask_username()
    assert app.user_var.get() == "Cool Mapper"
    assert app.settings.username_asked and app.settings.username == "Cool Mapper"
