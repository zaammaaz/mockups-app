"""main.py — Mockup Generator (CustomTkinter UI)."""

import datetime
import json
import os
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk

import theme

MODE_LOGO = "logo"
MODE_ARTWORK = "artwork"
MODE_VIDEO = "video"
VIDEO_EXTS = "*.mp4 *.mov *.webm *.avi *.mkv *.m4v"
IMAGE_FILETYPES = [
    ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.tif *.webp"),
    ("All files", "*.*"),
]
VIDEO_FILETYPES = [("Video files", VIDEO_EXTS), ("All files", "*.*")]

# Photoshop COM runs in a child process so a hung Photoshop (busy / Start screen /
# sign-in dialog on a managed PC) can be killed on timeout instead of freezing the app.
PS_PROBE_TIMEOUT = 20      # seconds to confirm Photoshop answers automation
PS_JOB_TIMEOUT = 240       # seconds per template (a video render can be slow)
_NO_WINDOW = 0x08000000    # subprocess.CREATE_NO_WINDOW (Windows)

BUILD = "2026-06-09a"      # bumped each build so the log shows which one ran


def _debug_log_path():
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "mockup-debug.log"


def _dlog(msg):
    """Append a timestamped line to mockup-debug.log (best-effort, flushed per line)."""
    try:
        with open(_debug_log_path(), "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%H:%M:%S.%f} [pid {os.getpid()}] {msg}\n")
    except Exception:
        pass


ctk.set_appearance_mode("dark")


class MockupGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        from config import load_config
        self._config = load_config()

        self.title("Mockup Generator")
        self.geometry("1320x840")
        self.minsize(1120, 720)
        self.configure(fg_color=theme.BG)

        self._mode = MODE_LOGO
        self._matches = {}
        self._jobs_to_process = []
        self._processing = False
        self._nav_buttons = {}
        self._mode_cards = {}

        # tk variables (handler logic depends on these names)
        self._client_name_var = tk.StringVar()
        self._logo_path_var = tk.StringVar()
        self._bg_color_var = tk.StringVar(value="#FFFFFF")
        self._hex_entry_var = tk.StringVar(value="#FFFFFF")
        self._logo_size_var = tk.IntVar(value=80)
        self._vertical_artwork_var = tk.StringVar()
        self._horizontal_artwork_var = tk.StringVar()
        self._square_artwork_var = tk.StringVar()
        self._vertical_video_var = tk.StringVar()
        self._horizontal_video_var = tk.StringVar()
        self._square_video_var = tk.StringVar()
        self._video_duration_var = tk.StringVar(value="10")
        self._templates_folder_var = tk.StringVar()
        self._output_folder_var = tk.StringVar()

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_center()
        self._build_right()
        self._load_saved_settings()
        self._select_mode(MODE_LOGO)

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _icon(self, name, size=(18, 18)):
        return theme.load_ctk_image(theme.asset_path("icons", name), size)

    def _card(self, parent, title=None, icon=None):
        card = ctk.CTkFrame(parent, corner_radius=theme.RADIUS_CARD, fg_color=theme.CARD)
        card.grid_columnconfigure(0, weight=1)
        if title:
            ctk.CTkLabel(card, text=f"  {title}", image=self._icon(icon, (16, 16)) if icon else None,
                         compound="left", font=(theme.FONT_FAMILY, 13, "bold"),
                         text_color=theme.TEXT).grid(row=0, column=0, sticky="w",
                                                     padx=theme.PAD_MD, pady=(theme.PAD_MD, theme.PAD_SM))
        return card

    def _browse_btn(self, parent, command):
        return ctk.CTkButton(parent, text="Browse", width=80, command=command,
                             fg_color=theme.CARD_HI, hover_color=theme.HAIRLINE,
                             text_color=theme.TEXT, corner_radius=theme.RADIUS_CTRL)

    def _entry(self, parent, var):
        return ctk.CTkEntry(parent, textvariable=var, fg_color=theme.BG,
                            border_color=theme.HAIRLINE, text_color=theme.TEXT,
                            corner_radius=theme.RADIUS_CTRL)

    def _path_row(self, parent, var, command, row):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=theme.PAD_MD, pady=(0, theme.PAD_SM))
        frame.grid_columnconfigure(0, weight=1)
        self._entry(frame, var).grid(row=0, column=0, sticky="ew")
        self._browse_btn(frame, command).grid(row=0, column=1, padx=(theme.PAD_SM, 0))
        return frame

    def _section(self, parent, text, row):
        ctk.CTkLabel(parent, text=text, font=(theme.FONT_FAMILY, 11),
                     text_color=theme.MUTED).grid(row=row, column=0, sticky="w",
                                                  padx=theme.PAD_MD, pady=(0, theme.PAD_XS))

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=224, corner_radius=0, fg_color=theme.SIDEBAR)
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(5, weight=1)

        head = ctk.CTkFrame(bar, fg_color="transparent")
        head.grid(row=0, column=0, sticky="w", padx=theme.PAD_MD, pady=(theme.PAD_LG, theme.PAD_LG))
        ctk.CTkLabel(head, text="  Mockup Generator", image=theme.logo_mark_image(30, "M"),
                     compound="left", font=(theme.FONT_FAMILY, 15, "bold"),
                     text_color=theme.TEXT).pack(side="left")

        modes = [(MODE_LOGO, "Logo Mode", "logo.png"),
                 (MODE_ARTWORK, "Artwork Mode", "artwork.png"),
                 (MODE_VIDEO, "Video Mode", "video.png")]
        for i, (m, label, icon) in enumerate(modes, start=1):
            btn = ctk.CTkButton(
                bar, text=label, image=self._icon(icon), compound="left", anchor="w",
                corner_radius=theme.RADIUS_CTRL, height=44,
                fg_color="transparent", hover_color=theme.CARD_HI,
                text_color=theme.TEXT, font=(theme.FONT_FAMILY, 12),
                command=lambda mm=m: self._select_mode(mm),
            )
            btn.grid(row=i, column=0, sticky="ew", padx=theme.PAD_SM, pady=2)
            self._nav_buttons[m] = btn

        footer = ctk.CTkFrame(bar, fg_color="transparent")
        footer.grid(row=6, column=0, sticky="ew", padx=theme.PAD_MD, pady=theme.PAD_MD)
        ctk.CTkLabel(footer, text="●  Ready", text_color=theme.SUCCESS,
                     font=(theme.FONT_FAMILY, 11)).pack(anchor="w", pady=(0, theme.PAD_SM))

    # ------------------------------------------------------------------
    # Center
    # ------------------------------------------------------------------
    def _build_center(self):
        self._center = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=theme.HAIRLINE, scrollbar_button_hover_color=theme.CARD_HI)
        self._center.grid(row=0, column=1, sticky="nsew", padx=theme.PAD_LG, pady=theme.PAD_MD)
        self._center.grid_columnconfigure(0, weight=1)
        r = 0

        # header (title + Help/theme toggle)
        header = ctk.CTkFrame(self._center, fg_color="transparent")
        header.grid(row=r, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_box, text="Mockup Generator", font=(theme.FONT_FAMILY, 26, "bold"),
                     text_color=theme.TEXT).pack(anchor="w")
        ctk.CTkLabel(title_box, text="Batch-generate branded product mockups from Photoshop templates.",
                     font=(theme.FONT_FAMILY, 12), text_color=theme.MUTED).pack(anchor="w")
        ctk.CTkButton(header, text="Help", image=self._icon("help.png", (16, 16)), compound="left",
                      width=80, command=self._show_help, fg_color="transparent", border_width=1,
                      border_color=theme.HAIRLINE, text_color=theme.TEXT).grid(row=0, column=1, padx=theme.PAD_XS)
        r += 1

        def gap():
            ctk.CTkFrame(self._center, fg_color="transparent", height=theme.PAD_MD).grid(row=r, column=0)

        # Client
        gap(); r += 1
        client = self._card(self._center, "Client", "client.png")
        client.grid(row=r, column=0, sticky="ew"); r += 1
        self._section(client, "Client name", 1)
        e = self._entry(client, self._client_name_var)
        e.configure(placeholder_text="Enter client or brand name")
        e.grid(row=2, column=0, sticky="ew", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))

        # Mode cards (one shown at a time)
        gap(); r += 1
        self._build_logo_card(r); r += 1
        self._build_artwork_card(r - 1)  # same grid row; shown/hidden
        self._build_video_card(r - 1)

        # Products
        gap(); r += 1
        prod = self._card(self._center, "Products", "box.png")
        prod.grid(row=r, column=0, sticky="ew"); r += 1
        ctk.CTkLabel(prod, text="One product name per line — matched by substring against PSD filenames.",
                     font=(theme.FONT_FAMILY, 11), text_color=theme.MUTED).grid(
            row=1, column=0, sticky="w", padx=theme.PAD_MD, pady=(0, theme.PAD_XS))
        self._products_text = ctk.CTkTextbox(prod, height=110, fg_color=theme.BG,
                                             border_color=theme.HAIRLINE, border_width=1,
                                             text_color=theme.TEXT, corner_radius=theme.RADIUS_CTRL,
                                             scrollbar_button_color=theme.HAIRLINE,
                                             scrollbar_button_hover_color=theme.CARD_HI)
        self._products_text.grid(row=2, column=0, sticky="ew", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))

        # Folders
        gap(); r += 1
        folders = self._card(self._center, "Folders", "folder.png")
        folders.grid(row=r, column=0, sticky="ew"); r += 1
        self._section(folders, "Templates folder", 1)
        self._path_row(folders, self._templates_folder_var, self._browse_templates, 2)
        self._section(folders, "Output folder", 3)
        self._path_row(folders, self._output_folder_var, self._browse_output, 4)
        ctk.CTkFrame(folders, fg_color="transparent", height=theme.PAD_XS).grid(row=5, column=0)

        # Actions
        gap(); r += 1
        actions = ctk.CTkFrame(self._center, fg_color="transparent")
        actions.grid(row=r, column=0, sticky="ew", pady=(0, theme.PAD_LG)); r += 1
        self._find_btn = ctk.CTkButton(actions, text="Find Templates",
                                       image=self._icon("search.png", (16, 16)), compound="left",
                                       command=self._find_templates, fg_color="transparent",
                                       border_width=1, border_color=theme.HAIRLINE,
                                       text_color=theme.TEXT, height=46, corner_radius=theme.RADIUS_CTRL)
        self._find_btn.pack(side="left", padx=(0, theme.PAD_SM))
        self._gen_img_on = theme.gradient_button_image((300, 46), "Generate Mockups", enabled=True)
        self._gen_img_off = theme.gradient_button_image((300, 46), "Generate Mockups", enabled=False)
        self._generate_btn = ctk.CTkButton(actions, text="", image=self._gen_img_off, width=300,
                                           command=self._generate_mockups, state="disabled",
                                           fg_color="transparent", hover=False)
        self._generate_btn.pack(side="left")

    def _build_logo_card(self, row):
        card = self._card(self._center, "Logo & Background", "image.png")
        card.grid(row=row, column=0, sticky="ew")
        self._mode_cards[MODE_LOGO] = card
        self._section(card, "Logo file", 1)
        zone = ctk.CTkFrame(card, fg_color="transparent")
        zone.grid(row=2, column=0, sticky="ew", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))
        zone.grid_columnconfigure(0, weight=1)
        self._logo_zone = ctk.CTkButton(zone, text="Click to upload logo\nPNG, JPG, SVG or PSD",
                                        height=64, command=self._browse_logo,
                                        fg_color=theme.BG, hover_color=theme.CARD_HI,
                                        text_color=theme.MUTED, border_width=1,
                                        border_color=theme.HAIRLINE, corner_radius=theme.RADIUS_CTRL)
        self._logo_zone.grid(row=0, column=0, sticky="ew")
        self._browse_btn(zone, self._browse_logo).grid(row=0, column=1, padx=(theme.PAD_SM, 0))
        self._logo_path_var.trace_add("write", lambda *a: self._update_logo_zone())

        self._section(card, "Background color", 3)
        color = ctk.CTkFrame(card, fg_color="transparent")
        color.grid(row=4, column=0, sticky="w", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))
        self._swatch = ctk.CTkFrame(color, width=32, height=32, corner_radius=8,
                                    fg_color=self._bg_color_var.get(), border_width=1,
                                    border_color=theme.HAIRLINE)
        self._swatch.grid(row=0, column=0, padx=(0, theme.PAD_SM)); self._swatch.grid_propagate(False)
        hexe = ctk.CTkEntry(color, textvariable=self._hex_entry_var, width=100, fg_color=theme.BG,
                            border_color=theme.HAIRLINE, text_color=theme.TEXT)
        hexe.grid(row=0, column=1, padx=(0, theme.PAD_SM))
        hexe.bind("<Return>", lambda e: self._apply_hex_entry())
        hexe.bind("<FocusOut>", lambda e: self._apply_hex_entry())
        ctk.CTkButton(color, text="Pick color", width=90, command=self._pick_color,
                      image=self._icon("palette.png", (14, 14)), compound="left",
                      fg_color=theme.CARD_HI, hover_color=theme.HAIRLINE,
                      text_color=theme.TEXT).grid(row=0, column=2)

        self._section(card, "Logo size", 5)
        srow = ctk.CTkFrame(card, fg_color="transparent")
        srow.grid(row=6, column=0, sticky="ew", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))
        srow.grid_columnconfigure(0, weight=1)
        self._size_label = ctk.CTkLabel(srow, text="80%", width=44, text_color=theme.TEXT)
        ctk.CTkSlider(srow, from_=10, to=100, variable=self._logo_size_var,
                      progress_color=theme.ACCENT, button_color=theme.ACCENT,
                      button_hover_color=theme.ACCENT,
                      command=lambda v: self._size_label.configure(text=f"{int(float(v))}%")
                      ).grid(row=0, column=0, sticky="ew", padx=(0, theme.PAD_SM))
        self._size_label.grid(row=0, column=1)

    _ORIENT_HINT = ("Matched by PSD filename (vertical / horizontal / square). "
                    "Provide any combination.")

    def _build_artwork_card(self, row):
        card = self._card(self._center, "Artwork Files", "image.png")
        card.grid(row=row, column=0, sticky="ew")
        self._mode_cards[MODE_ARTWORK] = card
        ctk.CTkLabel(card, text=self._ORIENT_HINT, font=(theme.FONT_FAMILY, 11),
                     text_color=theme.MUTED).grid(row=1, column=0, sticky="w",
                                                  padx=theme.PAD_MD, pady=(0, theme.PAD_SM))
        rows = [("Vertical artwork", self._vertical_artwork_var, "Select Vertical Artwork"),
                ("Horizontal artwork", self._horizontal_artwork_var, "Select Horizontal Artwork"),
                ("Square artwork", self._square_artwork_var, "Select Square Artwork")]
        r = 2
        for label, var, title in rows:
            self._section(card, label, r)
            self._path_row(card, var,
                           lambda v=var, t=title: self._browse_file(v, t, IMAGE_FILETYPES), r + 1)
            r += 2
        ctk.CTkFrame(card, fg_color="transparent", height=theme.PAD_XS).grid(row=r, column=0)

    def _build_video_card(self, row):
        card = self._card(self._center, "Video Artwork", "video.png")
        card.grid(row=row, column=0, sticky="ew")
        self._mode_cards[MODE_VIDEO] = card
        ctk.CTkLabel(card, text=self._ORIENT_HINT, font=(theme.FONT_FAMILY, 11),
                     text_color=theme.MUTED).grid(row=1, column=0, sticky="w",
                                                  padx=theme.PAD_MD, pady=(0, theme.PAD_SM))
        rows = [("Vertical video", self._vertical_video_var, "Select Vertical Video"),
                ("Horizontal video", self._horizontal_video_var, "Select Horizontal Video"),
                ("Square video", self._square_video_var, "Select Square Video")]
        r = 2
        for label, var, title in rows:
            self._section(card, label, r)
            self._path_row(card, var,
                           lambda v=var, t=title: self._browse_file(v, t, VIDEO_FILETYPES), r + 1)
            r += 2
        self._section(card, "Duration (seconds)", r)
        ctk.CTkEntry(card, textvariable=self._video_duration_var, width=90, fg_color=theme.BG,
                     border_color=theme.HAIRLINE, text_color=theme.TEXT).grid(
            row=r + 1, column=0, sticky="w", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))

    # ------------------------------------------------------------------
    # Right column
    # ------------------------------------------------------------------
    def _build_right(self):
        right = ctk.CTkFrame(self, width=330, corner_radius=0, fg_color="transparent")
        right.grid(row=0, column=2, sticky="nsew", padx=(0, theme.PAD_LG), pady=theme.PAD_MD)
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=2)
        right.grid_rowconfigure(2, weight=1)

        # Matched Templates
        matched = self._card(right, None)
        matched.grid(row=0, column=0, sticky="nsew", pady=(0, theme.PAD_MD))
        matched.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(matched, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=theme.PAD_MD, pady=theme.PAD_MD)
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="  Matched Templates", image=self._icon("folder.png", (16, 16)),
                     compound="left", font=(theme.FONT_FAMILY, 13, "bold"),
                     text_color=theme.TEXT).grid(row=0, column=0, sticky="w")
        self._match_count = ctk.CTkLabel(head, text="0", width=28, fg_color=theme.CARD_HI,
                                         corner_radius=8, text_color=theme.MUTED)
        self._match_count.grid(row=0, column=1)
        self._matches_textbox = ctk.CTkTextbox(matched, fg_color=theme.BG, border_width=0,
                                               text_color=theme.TEXT, corner_radius=theme.RADIUS_CTRL,
                                               font=(theme.FONT_FAMILY, 11),
                                               scrollbar_button_color=theme.HAIRLINE,
                                               scrollbar_button_hover_color=theme.CARD_HI)
        self._matches_textbox.grid(row=1, column=0, sticky="nsew", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))
        self._set_matches_text("No templates yet.\nFill in the fields and click Find Templates.")

        # Status
        status = self._card(right, None)
        status.grid(row=1, column=0, sticky="ew", pady=(0, theme.PAD_MD))
        self._status_var = tk.StringVar(value="Ready")
        ctk.CTkLabel(status, textvariable=self._status_var, font=(theme.FONT_FAMILY, 12, "bold"),
                     text_color=theme.TEXT).grid(row=0, column=0, sticky="w",
                                                 padx=theme.PAD_MD, pady=(theme.PAD_MD, theme.PAD_XS))
        self._progress = ctk.CTkProgressBar(status, progress_color=theme.ACCENT)
        self._progress.set(0)
        self._progress.grid(row=1, column=0, sticky="ew", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))

        # Log
        logc = self._card(right, None)
        logc.grid(row=2, column=0, sticky="nsew")
        logc.grid_rowconfigure(1, weight=1)
        lhead = ctk.CTkFrame(logc, fg_color="transparent")
        lhead.grid(row=0, column=0, sticky="ew", padx=theme.PAD_MD, pady=theme.PAD_MD)
        lhead.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(lhead, text="  Log", image=self._icon("log.png", (16, 16)), compound="left",
                     font=(theme.FONT_FAMILY, 13, "bold"), text_color=theme.TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(lhead, text="Clear", width=60, command=self._clear_log,
                      image=self._icon("clear.png", (14, 14)), compound="left",
                      fg_color=theme.CARD_HI, hover_color=theme.HAIRLINE,
                      text_color=theme.MUTED).grid(row=0, column=1)
        self._log_textbox = ctk.CTkTextbox(logc, fg_color=theme.BG, border_width=0, state="disabled",
                                           text_color=theme.TEXT, corner_radius=theme.RADIUS_CTRL,
                                           font=(theme.FONT_FAMILY, 11),
                                           scrollbar_button_color=theme.HAIRLINE,
                                           scrollbar_button_hover_color=theme.CARD_HI)
        self._log_textbox.grid(row=1, column=0, sticky="nsew", padx=theme.PAD_MD, pady=(0, theme.PAD_MD))

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------
    def _select_mode(self, mode):
        self._mode = mode
        for m, btn in self._nav_buttons.items():
            btn.configure(fg_color=theme.ACCENT if m == mode else "transparent")
        self._show_mode_card(mode)
        self._jobs_to_process = []
        if hasattr(self, "_generate_btn"):
            self._set_generate_enabled(False)
        if hasattr(self, "_matches_textbox"):
            self._set_matches_text("No templates yet.\nFill in the fields and click Find Templates.")
            self._match_count.configure(text="0")

    def _show_mode_card(self, mode):
        for m, card in self._mode_cards.items():
            card.grid() if m == mode else card.grid_remove()

    def _set_generate_enabled(self, enabled):
        self._generate_btn.configure(state="normal" if enabled else "disabled",
                                     image=self._gen_img_on if enabled else self._gen_img_off)

    def _update_logo_zone(self):
        name = Path(self._logo_path_var.get()).name
        self._logo_zone.configure(
            text=name if name else "Click to upload logo\nPNG, JPG, SVG or PSD")

    # ------------------------------------------------------------------
    # Header actions
    # ------------------------------------------------------------------
    def _show_help(self):
        messagebox.showinfo(
            "Help",
            "1. Pick a mode (Logo / Artwork / Video).\n"
            "2. Fill in client, files, products, and folders.\n"
            "3. Click Find Templates, then Generate Mockups.\n\n"
            "Video mode renders a short MP4 onto each matched screen template.",
        )

    # ------------------------------------------------------------------
    # Browsers / color / persistence  (logic ported from the Tk version)
    # ------------------------------------------------------------------
    def _browse_logo(self):
        path = filedialog.askopenfilename(title="Select Logo File", filetypes=IMAGE_FILETYPES)
        if path:
            self._logo_path_var.set(path)

    def _browse_file(self, var, title, filetypes):
        path = filedialog.askopenfilename(title=title, filetypes=filetypes)
        if path:
            var.set(path)

    def _browse_templates(self):
        folder = filedialog.askdirectory(title="Select Templates Folder")
        if folder:
            self._templates_folder_var.set(folder)
            self._save_folder_config()

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self._output_folder_var.set(folder)
            self._save_folder_config()

    def _pick_color(self):
        _, hex_color = colorchooser.askcolor(color=self._bg_color_var.get(),
                                             title="Select Background Color")
        if hex_color:
            self._set_bg_color(hex_color.upper())

    def _apply_hex_entry(self):
        raw = self._hex_entry_var.get().strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        if len(raw) == 7:
            try:
                int(raw[1:], 16)
                self._set_bg_color(raw.upper())
                return
            except ValueError:
                pass
        self._hex_entry_var.set(self._bg_color_var.get())

    def _set_bg_color(self, hex_color):
        self._bg_color_var.set(hex_color)
        self._hex_entry_var.set(hex_color)
        self._swatch.configure(fg_color=hex_color)

    def _load_saved_settings(self):
        self._templates_folder_var.set(self._config.get("templates_folder", ""))
        self._output_folder_var.set(self._config.get("output_folder", ""))

    def _save_folder_config(self):
        from config import save_config
        self._config["templates_folder"] = self._templates_folder_var.get()
        self._config["output_folder"] = self._output_folder_var.get()
        save_config(self._config)

    # ------------------------------------------------------------------
    # Thread-safe UI updates
    # ------------------------------------------------------------------
    def _log(self, message):
        def _append():
            self._log_textbox.configure(state="normal")
            self._log_textbox.insert("end", message + "\n")
            self._log_textbox.see("end")
            self._log_textbox.configure(state="disabled")
        self.after(0, _append)

    def _clear_log(self):
        self._log_textbox.configure(state="normal")
        self._log_textbox.delete("1.0", "end")
        self._log_textbox.configure(state="disabled")

    def _set_status(self, text):
        self.after(0, lambda: self._status_var.set(text))

    def _set_progress(self, value):
        self.after(0, lambda: self._progress.set(max(0.0, min(1.0, value / 100.0))))

    def _set_matches_text(self, text):
        self._matches_textbox.configure(state="normal")
        self._matches_textbox.delete("1.0", "end")
        self._matches_textbox.insert("1.0", text)
        self._matches_textbox.configure(state="disabled")

    # ------------------------------------------------------------------
    # Validation / inputs
    # ------------------------------------------------------------------
    def _get_product_names(self):
        raw = self._products_text.get("1.0", "end")
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _get_duration(self):
        try:
            return max(1, min(60, int(float(self._video_duration_var.get()))))
        except (ValueError, TypeError):
            return 10

    def _validate_inputs(self):
        if not self._client_name_var.get().strip():
            messagebox.showwarning("Missing Input", "Please enter a Client Name.")
            return False
        if self._mode == MODE_LOGO:
            if not self._logo_path_var.get().strip():
                messagebox.showwarning("Missing Input", "Please select a Logo File.")
                return False
        elif self._mode == MODE_ARTWORK:
            if not any(v.get().strip() for v in (self._vertical_artwork_var,
                                                 self._horizontal_artwork_var,
                                                 self._square_artwork_var)):
                messagebox.showwarning(
                    "Missing Input",
                    "Please select at least one artwork file (vertical, horizontal, or square).")
                return False
        elif self._mode == MODE_VIDEO:
            if not any(v.get().strip() for v in (self._vertical_video_var,
                                                 self._horizontal_video_var,
                                                 self._square_video_var)):
                messagebox.showwarning(
                    "Missing Input",
                    "Please select at least one video file (vertical, horizontal, or square).")
                return False
        if not self._get_product_names():
            messagebox.showwarning("Missing Input", "Please enter at least one Product name.")
            return False
        if not self._templates_folder_var.get().strip():
            messagebox.showwarning("Missing Input", "Please select a Templates Folder.")
            return False
        if not self._output_folder_var.get().strip():
            messagebox.showwarning("Missing Input", "Please select an Output Folder.")
            return False
        return True

    # ------------------------------------------------------------------
    # Find Templates
    # ------------------------------------------------------------------
    def _find_templates(self):
        if not self._validate_inputs():
            return
        self._set_generate_enabled(False)
        self._jobs_to_process = []
        from matcher import find_templates

        product_names = self._get_product_names()
        templates_folder = self._templates_folder_var.get().strip()
        self._set_status("Searching for templates…")
        try:
            matches = find_templates(templates_folder, product_names)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to search templates:\n{exc}")
            self._set_status("Search failed")
            return

        self._matches = matches
        jobs, skipped = self._build_job_list()

        lines = []
        for product, paths in matches.items():
            if paths:
                lines.append(f"{product}")
                for p in paths:
                    lines.append(f"    {p.name}")
            else:
                lines.append(f"{product}    (no match)")
        lines.extend(skipped)
        self._set_matches_text("\n".join(lines) if lines else "No templates found.")
        self._match_count.configure(text=str(len(jobs)))

        if not jobs:
            self._set_status("No matching templates")
            self._log("No matching templates found.")
            return
        self._jobs_to_process = jobs
        self._set_generate_enabled(True)
        self._set_status(f"{len(jobs)} template(s) matched — ready to generate")
        self._log(f"Found {len(jobs)} mockup(s) to generate.")

    def _build_job_list(self):
        from matcher import pick_oriented_file
        jobs, skipped = [], []
        for product, paths in self._matches.items():
            for psd_path in paths:
                if self._mode == MODE_LOGO:
                    jobs.append({
                        "product": product, "psd_path": psd_path,
                        "image_path": self._logo_path_var.get().strip(),
                        "bg_color": self._bg_color_var.get(),
                        "fill_fraction": self._logo_size_var.get() / 100.0,
                    })
                elif self._mode == MODE_ARTWORK:
                    chosen = pick_oriented_file(
                        psd_path, self._vertical_artwork_var.get().strip(),
                        self._horizontal_artwork_var.get().strip(),
                        self._square_artwork_var.get().strip())
                    if chosen is None:
                        skipped.append(f"    skipped: {psd_path.name} (no matching-orientation file)")
                        continue
                    jobs.append({"product": product, "psd_path": psd_path, "image_path": chosen})
                elif self._mode == MODE_VIDEO:
                    chosen = pick_oriented_file(
                        psd_path, self._vertical_video_var.get().strip(),
                        self._horizontal_video_var.get().strip(),
                        self._square_video_var.get().strip())
                    if chosen is None:
                        skipped.append(f"    skipped: {psd_path.name} (no matching-orientation file)")
                        continue
                    jobs.append({"product": product, "psd_path": psd_path,
                                 "video_path": chosen, "duration": self._get_duration()})
        return jobs, skipped

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------
    def _generate_mockups(self):
        if self._processing:
            return
        if not self._validate_inputs():
            return
        if not self._jobs_to_process:
            messagebox.showwarning("No Templates", "Please run 'Find Templates' first.")
            return
        if self._mode == MODE_VIDEO:
            import shutil
            import video
            if video.ffmpeg_path() == "ffmpeg" and shutil.which("ffmpeg") is None:
                messagebox.showerror("ffmpeg Missing",
                                     "Bundled ffmpeg not found and ffmpeg is not on PATH.")
                return

        _dlog(f"generate clicked: mode={self._mode} jobs={len(self._jobs_to_process)} "
              f"BUILD={BUILD} frozen={getattr(sys, 'frozen', False)}")
        self._processing = True
        self._find_btn.configure(state="disabled")
        self._set_generate_enabled(False)
        self._set_progress(0)
        self._set_status("Connecting to Photoshop…")
        threading.Thread(target=self._run_generation, daemon=True).start()

    def _run_generation(self):
        try:
            self._do_generation()
        finally:
            self.after(0, self._generation_done)

    def _do_generation(self):
        # Confirm Photoshop answers automation, in a child process with a hard timeout,
        # so a busy / Start-screen / dialog-blocked Photoshop can't freeze the app.
        _dlog("do_generation: begin probe")
        ok, msg = self._ps_probe(PS_PROBE_TIMEOUT)
        _dlog(f"do_generation: probe ok={ok}")
        if not ok:
            self._log(f"X {msg}")
            self._set_status("Photoshop not responding")
            return

        mode = self._mode
        client_name = self._client_name_var.get().strip()
        output_root = self._output_folder_var.get().strip()
        jobs = self._jobs_to_process
        total = len(jobs)
        success = failed = 0

        for idx, job in enumerate(jobs, start=1):
            psd_path = job["psd_path"]
            product = job["product"]
            output_dir = Path(output_root) / client_name
            output_dir.mkdir(parents=True, exist_ok=True)
            ext = "mp4" if mode == MODE_VIDEO else "jpg"
            output_path = output_dir / f"{client_name} - {product} - {psd_path.stem}.{ext}"

            payload = {"mode": mode, "psd_path": str(psd_path), "output_path": str(output_path)}
            if mode == MODE_LOGO:
                payload.update(image_path=job["image_path"], bg_color=job["bg_color"],
                               fill_fraction=job["fill_fraction"])
            elif mode == MODE_ARTWORK:
                payload.update(image_path=job["image_path"])
            else:
                payload.update(video_path=job["video_path"], duration=job["duration"])

            self._log(f"[{idx}/{total}] {product} - {psd_path.name}")
            self._set_status(f"Processing {idx}/{total}: {output_path.name}")
            ok, err = self._ps_run_job(payload, PS_JOB_TIMEOUT)
            if ok:
                self._log(f"  -> Saved {output_path.name}")
                success += 1
            else:
                self._log(f"  X {err}")
                failed += 1
            self._set_progress((idx / total) * 100)

        summary = f"Done · {success} succeeded · {failed} failed"
        self._log(summary)
        self._set_status(summary)

    # --- Photoshop runs in a child process (killable on timeout) ---------------
    def _child_cmd(self, *args):
        if getattr(sys, "frozen", False):
            return [sys.executable, *args]
        return [sys.executable, os.path.abspath(__file__), *args]

    def _ps_probe(self, timeout):
        cmd = self._child_cmd("--ps-probe")
        _dlog(f"ps_probe: spawn {cmd}")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                               creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            _dlog("ps_probe: TIMEOUT (child killed)")
            return False, ("Photoshop is open but not answering automation. Make sure it isn't "
                           "on the Start screen or showing a dialog — open a document (File > New), "
                           "dismiss any sign-in / license / update prompt — then click Generate again.")
        except Exception as exc:
            _dlog(f"ps_probe: spawn EXC {exc!r}")
            return False, f"Could not start the Photoshop helper: {exc}"
        _dlog(f"ps_probe: rc={r.returncode} stderr={r.stderr.strip()[:200]!r}")
        if r.returncode == 0:
            return True, ""
        return False, (r.stderr.strip() or "Could not connect to Photoshop. Make sure it is open.")

    def _ps_run_job(self, payload, timeout):
        fd, tmp = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            _dlog(f"ps_job: spawn {payload.get('mode')} -> {payload.get('output_path')}")
            r = subprocess.run(self._child_cmd("--ps-job", tmp), capture_output=True,
                               text=True, timeout=timeout, creationflags=_NO_WINDOW)
        except subprocess.TimeoutExpired:
            _dlog("ps_job: TIMEOUT (child killed)")
            return False, "timed out — Photoshop stopped responding (dismiss any Photoshop dialog, then retry)"
        except Exception as exc:
            _dlog(f"ps_job: spawn EXC {exc!r}")
            return False, f"helper error: {exc}"
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
        _dlog(f"ps_job: rc={r.returncode} stderr={r.stderr.strip()[:200]!r}")
        if r.returncode == 0:
            return True, ""
        return False, (r.stderr.strip()[-300:] or "failed")

    def _generation_done(self):
        self._processing = False
        self._find_btn.configure(state="normal")
        if self._jobs_to_process:
            self._set_generate_enabled(True)


def _child_probe():
    """Child process: confirm Photoshop answers automation. Prints version / errors."""
    _dlog("child probe: begin")
    import pythoncom
    pythoncom.CoInitialize()
    try:
        import photoshop as ps
        _dlog("child probe: connecting (GetActiveObject)")
        app = ps.ensure_photoshop()
        _dlog("child probe: connected, calling DoJavaScript")
        app.DoJavaScript("app.version")  # exercises the scripting path, not just connect
        _dlog("child probe: OK")
        return 0
    except Exception as exc:
        _dlog(f"child probe: ERROR {exc!r}")
        sys.stderr.write(str(exc))
        return 1
    finally:
        pythoncom.CoUninitialize()


def _child_job(job_file):
    """Child process: run one mockup job described by a JSON file."""
    _dlog(f"child job: begin {job_file}")
    import pythoncom
    pythoncom.CoInitialize()
    try:
        import photoshop as ps
        with open(job_file, encoding="utf-8") as f:
            d = json.load(f)
        mode = d["mode"]
        _dlog(f"child job: mode={mode} connecting")
        if mode == MODE_LOGO:
            ps.process_mockup(d["psd_path"], d["image_path"], d["bg_color"],
                              d["output_path"], fill_fraction=d["fill_fraction"])
        elif mode == MODE_ARTWORK:
            ps.process_mockup_artwork(d["psd_path"], d["image_path"], d["output_path"])
        else:
            import video
            video.make_video_mockup(d["psd_path"], d["video_path"], d["output_path"],
                                    duration=d["duration"], render_plate=ps.render_fill_plate)
        _dlog("child job: OK")
        return 0
    except Exception as exc:
        _dlog(f"child job: ERROR {exc!r}")
        sys.stderr.write(str(exc))
        return 1
    finally:
        pythoncom.CoUninitialize()


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--ps-probe":
        _dlog("main: --ps-probe child")
        sys.exit(_child_probe())
    if len(sys.argv) >= 3 and sys.argv[1] == "--ps-job":
        _dlog("main: --ps-job child")
        sys.exit(_child_job(sys.argv[2]))
    _dlog(f"main: GUI start BUILD={BUILD} frozen={getattr(sys, 'frozen', False)} exe={sys.executable}")
    app = MockupGeneratorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
