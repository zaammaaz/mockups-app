from PIL import Image

import theme


def test_make_gradient_size_mode_and_endpoints():
    img = theme.make_gradient((100, 20), ["#FF0000", "#0000FF"], "h")
    assert isinstance(img, Image.Image)
    assert img.size == (100, 20)
    assert img.mode == "RGBA"
    left = img.getpixel((0, 10))
    right = img.getpixel((99, 10))
    assert left[0] > 200 and left[2] < 60      # near red
    assert right[2] > 200 and right[0] < 60     # near blue


def test_make_gradient_vertical():
    img = theme.make_gradient((20, 100), ["#FF0000", "#0000FF"], "v")
    top = img.getpixel((10, 0))
    bottom = img.getpixel((10, 99))
    assert top[0] > 200 and bottom[2] > 200
