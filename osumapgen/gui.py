"""Tkinter desktop interface (no extra GUI dependencies)."""

from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import APP_NAME, __version__
from .deps import check_dependencies
from .infra import (Cancelled, Progress, STYLES, USERNAME_HINT, Settings, UserFacingError, check_username,
                    get_logger, setup_logging)

log = get_logger("gui")

SECTION_COLOURS = {"intro": "#7a8ca8", "verse": "#5b9bd5", "build": "#8e7cc3", "chorus": "#e06666",
                   "breakdown": "#76a5af", "outro": "#7a8ca8", "break": "#cccccc"}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.settings = Settings.load()
        self.q: "queue.Queue" = queue.Queue()
        self.worker = None
        self.progress = None
        self.result = None

        root.title(f"{APP_NAME} {__version__} - osu!standard beatmap generator")
        root.minsize(660, 640)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Big.TButton", font=("Segoe UI", 12, "bold"), padding=8)
        style.configure("Head.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("Stars.TLabel", font=("Segoe UI", 11))

        main = ttk.Frame(root, padding=14)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Generate an osu! beatmap from a song", style="Head.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))

        ttk.Label(main, text="Song (MP3):").grid(row=1, column=0, sticky="w")
        self.mp3_var = tk.StringVar(value=self.settings.last_mp3 if Path(self.settings.last_mp3).is_file() else "")
        ttk.Entry(main, textvariable=self.mp3_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(main, text="Browse...", command=self.browse).grid(row=1, column=2, sticky="ew")

        ttk.Label(main, text="Target stars:").grid(row=2, column=0, sticky="w", pady=6)
        sf = ttk.Frame(main)
        sf.grid(row=2, column=1, columnspan=2, sticky="w", padx=6)
        self.stars_var = tk.StringVar(value=f"{self.settings.stars:.1f}")
        ttk.Spinbox(sf, from_=0.5, to=12.0, increment=0.1, width=7, textvariable=self.stars_var).pack(side="left")
        ttk.Label(sf, text="   e.g. 2.0 easy  |  3.5 hard  |  5.0 insane  |  6.5+ expert",
                  foreground="#666").pack(side="left")

        ttk.Label(main, text="Mapping style:").grid(row=3, column=0, sticky="w")
        self.style_var = tk.StringVar(value=self.settings.style)
        ttk.Combobox(main, textvariable=self.style_var, values=STYLES, state="readonly", width=24).grid(
            row=3, column=1, sticky="w", padx=6)

        # osu! username (Creator) and optional details share row 4
        row4 = ttk.Frame(main)
        row4.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        row4.columnconfigure(1, weight=1)
        ttk.Label(row4, text="osu! username:").grid(row=0, column=0, sticky="w")
        self.user_var = tk.StringVar(value=self.settings.username)
        uf = ttk.Frame(row4)
        uf.grid(row=0, column=1, sticky="w", padx=(18, 0))
        ttk.Entry(uf, textvariable=self.user_var, width=20).pack(side="left")
        ttk.Label(uf, text="  CASE-SENSITIVE", foreground="#c0392b", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(uf, text="  (optional, needed only to upload)", foreground="#666").pack(side="left")
        ttk.Label(row4, text=USERNAME_HINT, foreground="#666", wraplength=560, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self.more = tk.BooleanVar(value=False)
        ttk.Checkbutton(row4, text="Optional details (title, artist, output folder)", variable=self.more,
                        command=self.toggle_more).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.more_frame = ttk.Frame(main)
        self.more_frame.columnconfigure(1, weight=1)
        self.title_var = tk.StringVar()
        self.artist_var = tk.StringVar()
        self.out_var = tk.StringVar(value=self.settings.output_dir)
        self.tol_var = tk.StringVar(value=str(self.settings.tolerance))
        self.meta_hint = tk.StringVar(value="")
        ttk.Label(self.more_frame, text="Title:").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.more_frame, textvariable=self.title_var).grid(row=0, column=1, sticky="ew", padx=6, pady=2)
        ttk.Label(self.more_frame, text="Artist:").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.more_frame, textvariable=self.artist_var).grid(row=1, column=1, sticky="ew", padx=6, pady=2)
        ttk.Label(self.more_frame, textvariable=self.meta_hint, foreground="#666").grid(
            row=2, column=1, sticky="w", padx=6)
        ttk.Label(self.more_frame, text="Output folder:").grid(row=3, column=0, sticky="w")
        ttk.Entry(self.more_frame, textvariable=self.out_var).grid(row=3, column=1, sticky="ew", padx=6, pady=2)
        ttk.Button(self.more_frame, text="Change...", command=self.choose_out).grid(row=3, column=2)
        ttk.Label(self.more_frame, text="Star tolerance (+/-):").grid(row=4, column=0, sticky="w")
        ttk.Spinbox(self.more_frame, from_=0.1, to=2.0, increment=0.1, width=6, textvariable=self.tol_var).grid(
            row=4, column=1, sticky="w", padx=6, pady=2)

        # actions
        act = ttk.Frame(main)
        act.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        act.columnconfigure(0, weight=1)
        self.gen_btn = ttk.Button(act, text="Generate", style="Big.TButton", command=self.generate)
        self.gen_btn.grid(row=0, column=0, sticky="ew")
        self.cancel_btn = ttk.Button(act, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.grid(row=0, column=1, padx=(8, 0))

        self.pbar = ttk.Progressbar(main, maximum=1000)
        self.pbar.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(6, 2))
        self.status = tk.StringVar(value="Choose an MP3, set the stars and press Generate.")
        ttk.Label(main, textvariable=self.status, wraplength=600).grid(row=8, column=0, columnspan=3, sticky="w")

        # results
        res = ttk.LabelFrame(main, text="Result", padding=8)
        res.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        main.rowconfigure(9, weight=1)
        res.columnconfigure(0, weight=1)
        self.stars_info = tk.StringVar(value="")
        ttk.Label(res, textvariable=self.stars_info, style="Stars.TLabel", justify="left").grid(
            row=0, column=0, sticky="w")
        self.canvas = tk.Canvas(res, height=56, background="#fafafa", highlightthickness=1,
                                highlightbackground="#ddd")
        self.canvas.grid(row=1, column=0, sticky="ew", pady=6)
        self.details = tk.Text(res, height=7, wrap="word", font=("Segoe UI", 9), relief="flat",
                               background=root.cget("background"))
        self.details.grid(row=2, column=0, sticky="nsew")
        res.rowconfigure(2, weight=1)
        self.details.configure(state="disabled")
        btns = ttk.Frame(res)
        btns.grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.open_folder_btn = ttk.Button(btns, text="Open Output Folder", command=self.open_folder,
                                          state="disabled")
        self.open_folder_btn.pack(side="left")
        self.open_osu_btn = ttk.Button(btns, text="Open in osu!", command=self.open_osu, state="disabled")
        self.open_osu_btn.pack(side="left", padx=6)
        self.report_btn = ttk.Button(btns, text="View Report", command=self.open_report, state="disabled")
        self.report_btn.pack(side="left")

        self.footer = tk.StringVar(value="")
        ttk.Label(main, textvariable=self.footer, foreground="#777").grid(row=10, column=0, columnspan=3,
                                                                          sticky="w", pady=(8, 0))
        self.root.after(50, self.startup_checks)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------ helpers
    def startup_checks(self):
        from .packaging import osu_client_name
        rep = check_dependencies()
        parts = []
        parts.append("FFmpeg: found" if rep.ffmpeg else "FFmpeg: not found (built-in MP3 decoder used)")
        client = osu_client_name()
        parts.append(f"osu!: {client}" if client else "osu!: not found (you can still import the .osz later)")
        self.footer.set("   |   ".join(parts) + "   |   Everything runs locally; nothing is uploaded.")
        if not rep.ok:
            messagebox.showerror(APP_NAME, rep.describe())
            self.gen_btn.configure(state="disabled")
        if self.mp3_var.get():
            self.prefill_metadata(self.mp3_var.get())
        if not self.settings.username_asked and not self.settings.username:
            self.ask_username()

    def ask_username(self):
        """First-run question. Skipping is fine: maps are then credited to 'OsuMapGen'."""
        prompt = ("What is your osu! username?\n\n"
                  "It is written into your maps as the Creator, which osu! checks if you upload one.\n\n"
                  "CASE-SENSITIVE: type it exactly as it appears on your osu! profile\n"
                  "(\"Peppy\" is not the same as \"peppy\").\n\n"
                  "Leave empty or press Cancel to skip. You can change it later in the main window.")
        name = ""
        for _ in range(3):
            answer = simpledialog.askstring(APP_NAME, prompt, initialvalue=name, parent=self.root)
            if answer is None:
                break
            name = answer.strip()
            problem = check_username(name)
            if not problem:
                break
            messagebox.showwarning(APP_NAME, problem)
        else:
            name = ""
        if name and not check_username(name):
            self.user_var.set(name)
            self.settings.username = name
        self.settings.username_asked = True
        self.settings.save()

    def toggle_more(self):
        if self.more.get():
            self.more_frame.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        else:
            self.more_frame.grid_forget()

    def browse(self):
        initial = self.settings.last_dir or str(Path.home() / "Music")
        path = filedialog.askopenfilename(title="Choose a song", initialdir=initial,
                                          filetypes=[("MP3 audio", "*.mp3"), ("OGG audio", "*.ogg"),
                                                     ("All files", "*.*")])
        if path:
            self.mp3_var.set(path)
            self.settings.last_dir = str(Path(path).parent)
            self.title_var.set("")
            self.artist_var.set("")
            self.prefill_metadata(path)

    def prefill_metadata(self, path):
        try:
            from .audio_io import probe
            info = probe(path)
        except Exception as e:  # shown later on Generate with a proper message
            self.meta_hint.set(f"Could not read tags: {e}")
            return
        src = []
        if info.title and not self.title_var.get():
            self.title_var.set(info.title)
            src.append("title")
        if info.artist and not self.artist_var.get():
            self.artist_var.set(info.artist)
            src.append("artist")
        if src:
            self.meta_hint.set("Filled from the file's tags: " + ", ".join(src) + ". Edit if needed.")
        else:
            self.meta_hint.set("No tags found: the file name will be used (Artist - Title) unless you type them.")
        self.status.set(f"Selected: {Path(path).name} ({info.duration_ms / 1000:.0f}s). Press Generate.")

    def choose_out(self):
        d = filedialog.askdirectory(initialdir=self.out_var.get() or str(Path.home()))
        if d:
            self.out_var.set(d)

    def set_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    # ------------------------------------------------------------ generation
    def generate(self):
        mp3 = self.mp3_var.get().strip().strip('"')
        if not mp3 or not Path(mp3).is_file():
            messagebox.showwarning(APP_NAME, "Please choose an MP3 file first.")
            return
        try:
            stars = float(self.stars_var.get().replace(",", "."))
            tol = float(self.tol_var.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning(APP_NAME, "The star rating must be a number such as 4.5.")
            return
        if not (0.5 <= stars <= 12):
            messagebox.showwarning(APP_NAME, "Please enter a star rating between 0.5 and 12.")
            return
        s = self.settings
        username = self.user_var.get()
        problem = check_username(username)
        if problem:
            messagebox.showwarning(APP_NAME, f"osu! username: {problem}\n\n{USERNAME_HINT}")
            return
        s.last_mp3, s.stars, s.style, s.output_dir, s.tolerance = mp3, stars, self.style_var.get(), \
            self.out_var.get(), tol
        s.username = username
        s.save()

        from .pipeline import GenerationRequest
        req = GenerationRequest(mp3_path=mp3, stars=stars, style=self.style_var.get(),
                                output_dir=self.out_var.get(), title=self.title_var.get() or None,
                                artist=self.artist_var.get() or None, tolerance=tol, offset_ms=s.offset_ms,
                                creator=username or None)
        self.progress = Progress(callback=lambda v, m: self.q.put(("progress", v, m)))
        self.gen_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        for b in (self.open_folder_btn, self.open_osu_btn, self.report_btn):
            b.configure(state="disabled")
        self.stars_info.set("")
        self.set_details("")
        self.canvas.delete("all")
        self.pbar["value"] = 0
        self.worker = threading.Thread(target=self._work, args=(req, self.progress), daemon=True)
        self.worker.start()
        self.root.after(100, self.poll)

    def _work(self, req, progress):
        from .pipeline import run
        try:
            res = run(req, progress)
            self.q.put(("done", res))
        except Cancelled:
            self.q.put(("cancelled",))
        except UserFacingError as e:
            self.q.put(("error", str(e), False))
        except Exception as e:
            log.error("Unexpected error\n%s", traceback.format_exc())
            self.q.put(("error", f"{type(e).__name__}: {e}", True))

    def cancel(self):
        if self.progress:
            self.progress.cancel()
            self.status.set("Cancelling...")

    def poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "progress":
                    self.pbar["value"] = msg[1] * 1000
                    self.status.set(msg[2])
                elif kind == "done":
                    self.finish(msg[1])
                    return
                elif kind == "cancelled":
                    self.reset_buttons()
                    self.status.set("Cancelled. Nothing was exported.")
                    return
                elif kind == "error":
                    self.reset_buttons()
                    from .infra import app_data_dir
                    extra = f"\n\nDetails were written to {app_data_dir() / 'osumapgen.log'}" if msg[2] else ""
                    self.status.set("Error: " + msg[1])
                    messagebox.showerror(APP_NAME, msg[1] + extra)
                    return
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def reset_buttons(self):
        self.gen_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def finish(self, res):
        self.result = res
        self.reset_buttons()
        self.pbar["value"] = 1000 if res.ok else self.pbar["value"]
        self.status.set(res.message)
        if res.estimated_stars is not None:
            mark = "within tolerance" if res.within_tolerance else "OUTSIDE tolerance - see notes"
            self.stars_info.set(
                f"Requested: {res.requested_stars:.2f} stars     Estimated: {res.estimated_stars:.2f} stars "
                f"(lazer)  /  {res.estimated_stars_stable:.2f} (stable)   [{mark}]\n"
                f"osu! client rating: shown in-game after import (not read automatically)     "
                f"Style: {res.style_used}     Coverage: {res.coverage_pct or 0:.0f}%")
        notes = []
        if res.errors:
            notes.append("Problems:\n" + "\n".join("  - " + e for e in res.errors[:12]))
        if res.warnings:
            notes.append("Notes:\n" + "\n".join("  - " + w for w in res.warnings[:12]))
        if res.style_breakdown:
            notes.insert(0, res.style_breakdown)
        if res.osz_path:
            notes.insert(0, f"Package: {res.osz_path}")
        self.set_details("\n\n".join(notes))
        self.draw_timeline(res)
        if res.output_folder:
            self.open_folder_btn.configure(state="normal")
        if res.report_path:
            self.report_btn.configure(state="normal")
        if res.osz_path:
            self.open_osu_btn.configure(state="normal")
        if not res.ok:
            messagebox.showwarning(APP_NAME, res.message)

    def draw_timeline(self, res):
        c = self.canvas
        c.delete("all")
        c.update_idletasks()
        w = max(200, c.winfo_width())
        h = int(c.cget("height"))
        tl = res.timeline
        if not tl:
            return
        top = max(n for _, n in tl) or 1
        bw = w / len(tl)
        for i, (_, n) in enumerate(tl):
            bh = (h - 14) * n / top
            c.create_rectangle(i * bw, h - 12 - bh, (i + 1) * bw - 1, h - 12, fill="#e8649a", width=0)
        total = tl[-1][0] + 2
        for k in range(0, int(total) + 1, 30):
            x = k / total * w
            c.create_text(x + 2, h - 6, text=f"{k // 60}:{k % 60:02d}", anchor="w", font=("Segoe UI", 7),
                          fill="#888")
        c.create_text(4, 4, text="objects over time (whole song)", anchor="nw", font=("Segoe UI", 7), fill="#888")

    # ------------------------------------------------------------ result actions
    def open_folder(self):
        from .packaging import open_folder
        if self.result and self.result.output_folder:
            open_folder(Path(self.result.output_folder))

    def open_osu(self):
        from .packaging import open_in_osu
        if self.result and self.result.osz_path:
            self.status.set(open_in_osu(Path(self.result.osz_path)))

    def open_report(self):
        from .packaging import open_folder
        if self.result and self.result.report_path:
            open_folder(Path(self.result.report_path))

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME, "A map is being generated. Cancel it and quit?"):
                return
            if self.progress:
                self.progress.cancel()
        self.root.destroy()


def run_gui():
    setup_logging()
    try:  # crisp text on high-DPI screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    App(root)
    root.mainloop()
