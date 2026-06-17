"""
Tests for creatives/upload.py.
Mocks the Supabase client — no real storage or DB calls.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from creatives.upload import upload_creative

FAKE_BRAND_ID = "9759c4a8-212c-496a-a907-22a471bdcba5"
FAKE_SIGNED_URL = "https://test.supabase.co/storage/v1/sign/creatives/fake-path"
ENV = {
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
}


def _make_sb(bucket_exists: bool = False):
    """
    Returns (mock_sb, creatives_table_mock).
    Wires up brands → one row, storage → no-op upload + signed URL.
    """
    sb = MagicMock()

    brands_mock = MagicMock()
    brands_mock.select.return_value.execute.return_value.data = [{"id": FAKE_BRAND_ID}]

    creatives_mock = MagicMock()

    def _table(name):
        return brands_mock if name == "brands" else creatives_mock

    sb.table.side_effect = _table

    if bucket_exists:
        existing_bucket = MagicMock()
        existing_bucket.name = "creatives"
        sb.storage.list_buckets.return_value = [existing_bucket]
    else:
        sb.storage.list_buckets.return_value = []
    sb.storage.from_.return_value.upload.return_value = None
    sb.storage.from_.return_value.create_signed_url.return_value = {
        "signedURL": FAKE_SIGNED_URL
    }

    return sb, creatives_mock


# ── insert payload ────────────────────────────────────────────────────────────

def test_insert_payload_video(tmp_path):
    f = tmp_path / "ugc_ad.mp4"
    f.write_bytes(b"fake-video")
    sb, creatives = _make_sb()

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV):
        creative_id = upload_creative(str(f))

    payload = creatives.insert.call_args[0][0]
    assert payload["id"] == creative_id
    assert payload["brand_id"] == FAKE_BRAND_ID
    assert payload["file_url"] == FAKE_SIGNED_URL
    assert payload["file_type"] == "video"
    assert payload["ad_id"] is None


def test_insert_payload_image_inferred(tmp_path):
    f = tmp_path / "banner.jpg"
    f.write_bytes(b"fake-image")
    sb, creatives = _make_sb()

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV):
        upload_creative(str(f))

    assert creatives.insert.call_args[0][0]["file_type"] == "image"


def test_explicit_type_overrides_extension(tmp_path):
    f = tmp_path / "deck.pdf"
    f.write_bytes(b"data")
    sb, creatives = _make_sb()

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV):
        upload_creative(str(f), file_type="carousel")

    assert creatives.insert.call_args[0][0]["file_type"] == "carousel"


def test_ad_id_passed_through(tmp_path):
    f = tmp_path / "ad.mp4"
    f.write_bytes(b"data")
    sb, creatives = _make_sb()

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV):
        upload_creative(str(f), ad_id="120215998064080350")

    assert creatives.insert.call_args[0][0]["ad_id"] == "120215998064080350"


# ── storage bucket handling ───────────────────────────────────────────────────

def test_bucket_created_when_missing(tmp_path):
    f = tmp_path / "ad.mp4"
    f.write_bytes(b"data")
    sb, _ = _make_sb(bucket_exists=False)

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV):
        upload_creative(str(f))

    sb.storage.create_bucket.assert_called_once_with(
        "creatives", options={"public": False}
    )


def test_bucket_not_recreated_when_exists(tmp_path):
    f = tmp_path / "ad.mp4"
    f.write_bytes(b"data")
    sb, _ = _make_sb(bucket_exists=True)

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV):
        upload_creative(str(f))

    sb.storage.create_bucket.assert_not_called()


# ── validation ────────────────────────────────────────────────────────────────

def test_unknown_extension_without_explicit_type_exits(tmp_path):
    f = tmp_path / "weird.xyz"
    f.write_bytes(b"data")
    sb, _ = _make_sb()

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV), \
         pytest.raises(SystemExit):
        upload_creative(str(f))


def test_missing_file_exits(tmp_path):
    sb, _ = _make_sb()

    with patch("creatives.upload.create_client", return_value=sb), \
         patch.dict(os.environ, ENV), \
         pytest.raises(SystemExit):
        upload_creative(str(tmp_path / "does_not_exist.mp4"))
