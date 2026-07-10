from pathlib import Path

from idgod_order_cli.orderer import _extract_order_error, _prepare_upload_image


def test_prepare_upload_image_converts_webp(tmp_path):
  src = tmp_path / "photo.webp"
  # minimal 1x1 webp header-ish not needed; use png via pillow
  from PIL import Image
  img = Image.new("RGB", (10, 10), color=(255, 0, 0))
  img.save(src, "WEBP")
  out = _prepare_upload_image(src)
  assert out.suffix.lower() == ".jpg"
  assert out.stat().st_size > 0


def test_extract_order_error():
  body = "We couldn't add that card — please check the highlighted fields below."
  assert "couldn't add" in _extract_order_error(body).lower()
