"""Visual tokens, asset helpers, and Pillow gradient generation for the CTk UI."""

import sys
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

# ---- Colors ----
BG = "#0B0F1A"
SIDEBAR = "#0E1320"
CARD = "#161B2B"
CARD_HI = "#1C2233"
HAIRLINE = "#2A3142"
TEXT = "#E5E7EB"
MUTED = "#9CA3AF"
SUCCESS = "#22C55E"
ACCENT = "#8B5CF6"
ACCENT_STOPS = ["#EC4899", "#8B5CF6", "#3B82F6"]  # pink -> purple -> blue

# ---- Fonts ----
FONT_FAMILY = "Segoe UI Variable"

# ---- Spacing / radius ----
PAD_XS, PAD_SM, PAD_MD, PAD_LG = 4, 8, 16, 24
RADIUS_CARD, RADIUS_CTRL = 16, 10


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).parent


def asset_path(*parts) -> Path:
    return base_dir() / "assets" / Path(*parts)


def _hex(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def make_gradient(size, stops, direction="h"):
    """Return an RGBA gradient Image of `size` interpolating hex `stops`."""
    w, h = size
    rgb_stops = [_hex(s) for s in stops]
    n = len(rgb_stops)
    length = w if direction == "h" else h
    line = Image.new("RGBA", (length, 1))
    px = line.load()
    for i in range(length):
        t = i / max(1, length - 1)
        seg = t * (n - 1)
        k = min(int(seg), n - 2)
        f = seg - k
        a, b = rgb_stops[k], rgb_stops[k + 1]
        r = round(a[0] + (b[0] - a[0]) * f)
        g = round(a[1] + (b[1] - a[1]) * f)
        bl = round(a[2] + (b[2] - a[2]) * f)
        px[i, 0] = (r, g, bl, 255)
    if direction == "h":
        return line.resize((w, h))
    return line.rotate(-90, expand=True).resize((w, h))


def gradient_png(name, size, stops, direction="h"):
    """Generate (and cache) a gradient PNG under assets/generated/; return its path."""
    out = base_dir() / "assets" / "generated" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        make_gradient(size, stops, direction).save(out)
    return out


def load_ctk_image(path, size):
    """Load a PNG as a CTkImage, or return None if missing (caller shows text fallback)."""
    p = Path(path)
    if not p.exists():
        return None
    img = Image.open(p).convert("RGBA")
    return ctk.CTkImage(light_image=img, dark_image=img, size=size)


def _rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                                           radius=radius, fill=255)
    return mask


def rounded_gradient_image(size, stops, radius=12, direction="h"):
    """A CTkImage: gradient with rounded-rect alpha (for the hero Generate button)."""
    grad = make_gradient(size, stops, direction)
    grad.putalpha(_rounded_mask(size, radius))
    return ctk.CTkImage(light_image=grad, dark_image=grad, size=size)


def gradient_button_image(size, text, enabled=True, radius=12):
    """A CTkImage of a rounded gradient (or muted) button with centered white text."""
    ss = 2
    w, h = size[0] * ss, size[1] * ss
    if enabled:
        img = make_gradient((w, h), ACCENT_STOPS, "h")
    else:
        img = Image.new("RGBA", (w, h), _hex(CARD_HI) + (255,))
    img.putalpha(_rounded_mask((w, h), radius * ss))
    draw = ImageDraw.Draw(img)
    font = _font(int(h * 0.40))
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    fill = (255, 255, 255, 255) if enabled else _hex(MUTED) + (255,)
    draw.text(((w - tw) / 2 - box[0], (h - th) / 2 - box[1]), text, font=font, fill=fill)
    img = img.resize(size, Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=size)


def _font(px):
    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def logo_mark_image(px=30, letter="M", radius=8):
    """A gradient rounded square brand mark with a white letter (e.g. 'M')."""
    ss = 4  # supersample for crisp edges
    size = (px * ss, px * ss)
    grad = make_gradient(size, ACCENT_STOPS, "h")
    grad.putalpha(_rounded_mask(size, radius * ss))
    draw = ImageDraw.Draw(grad)
    font = _font(int(px * ss * 0.62))
    box = draw.textbbox((0, 0), letter, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    draw.text(((size[0] - tw) / 2 - box[0], (size[1] - th) / 2 - box[1]),
              letter, font=font, fill=(255, 255, 255, 255))
    grad = grad.resize((px, px), Image.LANCZOS)
    return ctk.CTkImage(light_image=grad, dark_image=grad, size=(px, px))
