import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

import video


def test_ffmpeg_path_returns_bundled_binary():
    p = video.ffmpeg_path()
    assert p.endswith("ffmpeg.exe")
    assert Path(p).exists()


def _make_marker(path, size=(400, 300)):
    quad = [(60, 40), (320, 70), (300, 250), (80, 210)]  # TL, TR, BR, BL
    im = Image.new("RGB", size, (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.polygon(quad, fill=(255, 0, 255))
    # scattered reflection-like noise (separate small blob) — must be ignored
    d.rectangle([5, 290, 12, 297], fill=(255, 0, 255))
    im.save(path)
    return quad


def _close(a, b, tol=4):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def test_detect_quad_finds_corners_and_rejects_noise(tmp_path):
    p = tmp_path / "marker.png"
    quad = _make_marker(p)
    size, tl, tr, br, bl = video.detect_quad(p)
    assert size == (400, 300)
    assert _close(tl, quad[0])
    assert _close(tr, quad[1])
    assert _close(br, quad[2])
    assert _close(bl, quad[3])


def test_detect_quad_downscales_large_canvas(tmp_path):
    # Large (>work_max) plate: detection runs downscaled, corners scale back to full res.
    quad = [(300, 200), (1700, 350), (1650, 1300), (400, 1150)]  # TL, TR, BR, BL
    p = tmp_path / "big_marker.png"
    im = Image.new("RGB", (2000, 1500), (0, 0, 0))
    ImageDraw.Draw(im).polygon(quad, fill=(255, 0, 255))
    im.save(p)
    size, tl, tr, br, bl = video.detect_quad(p)
    assert size == (2000, 1500)
    assert _close(tl, quad[0], tol=12)
    assert _close(tr, quad[1], tol=12)
    assert _close(br, quad[2], tol=12)
    assert _close(bl, quad[3], tol=12)


def test_build_mask_polygon(tmp_path):
    out = tmp_path / "mask.png"
    corners = [(10, 10), (90, 10), (90, 90), (10, 90)]
    video.build_mask((100, 100), corners, out)
    m = Image.open(out)
    assert m.size == (100, 100)
    assert m.getpixel((50, 50)) == 255
    assert m.getpixel((2, 2)) == 0


def _synth_video(path, seconds=3, size="320x240"):
    subprocess.run(
        [video.ffmpeg_path(), "-y", "-f", "lavfi",
         "-i", f"testsrc2=size={size}:rate=30", "-t", str(seconds),
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def test_render_video_loop_and_trim(tmp_path):
    vid = tmp_path / "v.mp4"
    _synth_video(vid, seconds=3)
    bg = tmp_path / "bg.png"
    Image.new("RGB", (640, 480), (20, 20, 20)).save(bg)
    corners = [(100, 100), (500, 120), (520, 400), (120, 380)]
    mask = tmp_path / "mask.png"
    video.build_mask((640, 480), corners, mask)
    out = tmp_path / "out.mp4"
    video.render_video(vid, bg, mask, (640, 480), corners, out, duration=5, fps=30)
    assert out.exists() and out.stat().st_size > 0
    probe = subprocess.run([video.ffmpeg_path(), "-i", str(out)],
                           capture_output=True, text=True)
    assert "Duration: 00:00:05" in probe.stderr


def test_render_video_trims_long_source(tmp_path):
    # Source longer than duration -> trimmed to exact duration (the trim branch).
    vid = tmp_path / "v.mp4"
    _synth_video(vid, seconds=6)
    bg = tmp_path / "bg.png"
    Image.new("RGB", (640, 480), (20, 20, 20)).save(bg)
    corners = [(100, 100), (500, 120), (520, 400), (120, 380)]
    mask = tmp_path / "mask.png"
    video.build_mask((640, 480), corners, mask)
    out = tmp_path / "out.mp4"
    video.render_video(vid, bg, mask, (640, 480), corners, out, duration=2, fps=30)
    probe = subprocess.run([video.ffmpeg_path(), "-i", str(out)],
                           capture_output=True, text=True)
    assert "Duration: 00:00:02" in probe.stderr


def test_make_video_mockup_end_to_end(tmp_path):
    vid = tmp_path / "v.mp4"
    _synth_video(vid, seconds=2)
    quad = [(80, 60), (360, 90), (340, 300), (100, 260)]

    def fake_plate(psd_path, rgb, out_png):
        im = Image.new("RGB", (480, 360), (0, 0, 0))
        ImageDraw.Draw(im).polygon(quad, fill=rgb)
        im.save(out_png)

    out = tmp_path / "m.mp4"
    video.make_video_mockup("ignored.psd", vid, out, duration=4, fps=30,
                            render_plate=fake_plate)
    assert out.exists()
    probe = subprocess.run([video.ffmpeg_path(), "-i", str(out)],
                           capture_output=True, text=True)
    assert "Duration: 00:00:04" in probe.stderr
