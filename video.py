"""Video mockup pipeline: corner detection, masking, ffmpeg compositing.

Pure Python (Pillow + bundled ffmpeg). No Photoshop import — the Photoshop
plate render is injected as a callback so this module is testable standalone.
"""

import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

FPS_DEFAULT = 30
DURATION_DEFAULT = 10


def ffmpeg_path() -> str:
    """Locate the bundled ffmpeg; fall back to PATH."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        cand = base / "ffmpeg" / "ffmpeg.exe"
        if cand.exists():
            return str(cand)
    dev = Path(__file__).parent / "tools" / "ffmpeg" / "ffmpeg.exe"
    if dev.exists():
        return str(dev)
    return "ffmpeg"


def _magenta_mask(im):
    """Brightness-tolerant magenta mask: R and B strong, both clearly above G."""
    r, g, b = im.split()
    min_rb = ImageChops.darker(r, b)
    diff = ImageChops.subtract(min_rb, g)
    hue = diff.point(lambda v: 255 if v >= 100 else 0).convert("1")
    bright = min_rb.point(lambda v: 255 if v >= 80 else 0).convert("1")
    return ImageChops.logical_and(hue, bright)


def _largest_blob(m):
    W, H = m.size
    data = m.load()
    visited = bytearray(W * H)
    best = []
    for y0 in range(H):
        base = y0 * W
        for x0 in range(W):
            if data[x0, y0] and not visited[base + x0]:
                comp = []
                dq = deque([(x0, y0)])
                visited[base + x0] = 1
                while dq:
                    cx, cy = dq.popleft()
                    comp.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < W and 0 <= ny < H and data[nx, ny] and not visited[ny * W + nx]:
                            visited[ny * W + nx] = 1
                            dq.append((nx, ny))
                if len(comp) > len(best):
                    best = comp
    return best


def _corners(comp):
    INF = 10 ** 9
    btl, btr, bbr, bbl = INF, -INF, -INF, INF
    ptl = ptr = pbr = pbl = None
    for x, y in comp:
        s, d = x + y, x - y
        if s < btl: btl, ptl = s, (x, y)
        if s > bbr: bbr, pbr = s, (x, y)
        if d > btr: btr, ptr = d, (x, y)
        if d < bbl: bbl, pbl = d, (x, y)
    return ptl, ptr, pbr, pbl


DETECT_WORK_MAX = 1400


def detect_quad(marker_png, work_max=DETECT_WORK_MAX):
    """Return (size, tl, tr, br, bl) of the artwork quad in a magenta marker plate.

    Detection runs on a downscaled copy (longest edge <= work_max) so the pure-Python
    blob fill stays fast on large (4K+) plates; corners are scaled back to full size.
    The returned size is always the full-resolution plate size.
    """
    im = Image.open(marker_png).convert("RGB")
    W, H = im.size
    longest = max(W, H)
    scale = work_max / longest if longest > work_max else 1.0
    work = im if scale == 1.0 else im.resize(
        (max(1, round(W * scale)), max(1, round(H * scale))), Image.BILINEAR
    )

    comp = _largest_blob(_magenta_mask(work))
    if not comp:
        raise ValueError(f"No artwork region detected in {marker_png}")
    tl, tr, br, bl = _corners(comp)

    if scale != 1.0:
        inv = 1.0 / scale
        tl, tr, br, bl = (
            (round(p[0] * inv), round(p[1] * inv)) for p in (tl, tr, br, bl)
        )
    return im.size, tl, tr, br, bl


def build_mask(size, corners, out_png):
    """Write an L-mode alpha mask for the quad with an anti-aliased edge.

    The background plate is black *inside* the screen region, so the quad
    interior must stay fully opaque (partial alpha there would reveal black).
    We therefore dilate ~1px to keep the interior solid and feather only the
    outer edge into the surrounding product, removing the jagged 1px boundary.
    """
    tl, tr, br, bl = corners
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon([tl, tr, br, bl], fill=255)
    mask = mask.filter(ImageFilter.MaxFilter(3))      # dilate ~1px: interior stays opaque
    mask = mask.filter(ImageFilter.GaussianBlur(1.0))  # soften only the outer edge
    mask.save(out_png)
    return out_png


def render_video(video_in, bg_png, mask_png, size, corners, out_mp4,
                 duration=DURATION_DEFAULT, fps=FPS_DEFAULT, ffmpeg_exe=None):
    """Loop/trim video to `duration`, perspective-warp into the quad, mask, overlay on bg."""
    ffmpeg_exe = ffmpeg_exe or ffmpeg_path()
    W, H = size
    tl, tr, br, bl = corners
    fc = (
        f"[0:v]fps={fps},scale={W}:{H},setsar=1,"
        f"perspective={tl[0]}:{tl[1]}:{tr[0]}:{tr[1]}:{bl[0]}:{bl[1]}:{br[0]}:{br[1]}:sense=destination[w];"
        f"[w][2:v]alphamerge[wa];"
        f"[1:v][wa]overlay=0:0[out]"
    )
    cmd = [
        ffmpeg_exe, "-y", "-stream_loop", "-1", "-i", str(video_in),
        "-i", str(bg_png), "-i", str(mask_png), "-filter_complex", fc,
        "-map", "[out]", "-t", str(duration), "-r", str(fps),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", str(out_mp4),
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError(
            f"ffmpeg not found. Expected at: {ffmpeg_exe}\n"
            "Bundle tools/ffmpeg/ffmpeg.exe or add ffmpeg to PATH."
        )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{p.stderr[-2000:]}")
    return out_mp4


def make_video_mockup(psd_path, video_in, out_mp4, duration=DURATION_DEFAULT,
                      fps=FPS_DEFAULT, render_plate=None):
    """Full pipeline. `render_plate(psd_path, (r,g,b), out_png)` renders a flattened
    plate with the artwork smart object filled solid — injected so this is testable
    without Photoshop. In the app, pass `photoshop.render_fill_plate`."""
    if render_plate is None:
        raise ValueError("render_plate callback is required")
    work = Path(tempfile.mkdtemp(prefix="mockvid_"))
    try:
        marker = work / "marker.png"
        bg = work / "bg.png"
        mask = work / "mask.png"
        render_plate(psd_path, (255, 0, 255), marker)
        render_plate(psd_path, (0, 0, 0), bg)
        size, tl, tr, br, bl = detect_quad(marker)
        build_mask(size, (tl, tr, br, bl), mask)
        render_video(video_in, bg, mask, size, (tl, tr, br, bl), out_mp4,
                     duration=duration, fps=fps)
        return out_mp4
    finally:
        shutil.rmtree(work, ignore_errors=True)
