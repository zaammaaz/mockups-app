# Mockup Generator

Windows desktop app that batch-generates product mockups from Photoshop (`.psd`) templates. Point it at a folder of mockup templates and a client's logo, artwork, or video, and it fills every matching template automatically — no manual Photoshop work per template.

Built with CustomTkinter for the UI, driving Photoshop over COM automation (ExtendScript) to do the actual rendering.

## What it does

Three modes, selectable from the sidebar:

- **Logo Mode** — drops a client logo onto every matching template at a chosen size/position, with a configurable background color.
- **Artwork Mode** — fills template smart objects with static artwork. Supports separate vertical, horizontal, and square source images, auto-picked per template based on the template's orientation (detected from its filename).
- **Video Mode** — same orientation-matching idea, but renders the artwork as video frames into the template (for templates meant to preview motion content, e.g. screens/billboards).

### How matching works

- Templates are matched to products by **substring search** on filename/path (e.g. a product named "Mug" matches any `.psd` whose path contains "mug").
- For Artwork/Video mode, each template's **orientation** is read from its filename (`square` / `horizontal` / `vertical`) and the matching source file is picked automatically. Precedence: square > horizontal > vertical. A template with no orientation keyword, or whose orientation file wasn't supplied, is skipped.

### Requirements

- Adobe Photoshop must already be **open** — the app connects to a running instance via COM, it does not launch Photoshop itself.
- Windows only (COM automation, `pywin32`).

## Running

```
python main.py
```

Or run the packaged build: `dist/MockupGenerator/MockupGenerator.exe` (build with `pyinstaller MockupGenerator.spec`).

## Project layout

- `main.py` — UI and app flow (CustomTkinter)
- `photoshop.py` — Photoshop automation via ExtendScript/COM
- `matcher.py` — template discovery + orientation/product matching
- `video.py` — video-frame handling for Video Mode
- `theme.py` — UI styling/asset helpers
- `config.py` — persists last-used folders/settings to `config.json`
- `tools/ffmpeg/` — bundled ffmpeg binary (video mode, downloaded at build time)
