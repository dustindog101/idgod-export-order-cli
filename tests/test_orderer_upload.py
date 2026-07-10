from pathlib import Path

from PIL import Image

from idgod_order_cli.orderer import _extract_order_error, _prepare_upload_image


def test_jpeg_passthrough_without_optimize(tmp_path):
    src = tmp_path / "photo.jpg"
    img = Image.new("RGB", (2000, 2000), color=(10, 20, 30))
    img.save(src, "JPEG", quality=95)
    out = _prepare_upload_image(src, optimize=False)
    assert out == src


def test_webp_converts_without_resize(tmp_path):
    src = tmp_path / "photo.webp"
    img = Image.new("RGB", (2400, 1800), color=(255, 0, 0))
    img.save(src, "WEBP")
    out = _prepare_upload_image(src, optimize=False)
    assert out.suffix.lower() == ".jpg"
    with Image.open(out) as converted:
        assert converted.size == (2400, 1800)


def test_optimize_downscales_large_webp(tmp_path):
    src = tmp_path / "photo.webp"
    img = Image.new("RGB", (2400, 1800), color=(255, 0, 0))
    img.save(src, "WEBP")
    plain = _prepare_upload_image(src, optimize=False)
    small = _prepare_upload_image(src, optimize=True)
    with Image.open(small) as converted:
        assert max(converted.size) <= 1800
    assert small.stat().st_size < plain.stat().st_size


def test_extract_order_error():
    body = "We couldn't add that card — please check the highlighted fields below."
    assert "couldn't add" in _extract_order_error(body).lower()
