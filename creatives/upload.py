"""
Upload a creative file (video or image) to Supabase Storage and register it
in the `creatives` table.

Usage:
    python creatives/upload.py <file_path> [--type video|image|carousel] [--ad-id <meta_ad_id>]

Examples:
    python creatives/upload.py ~/Desktop/kesar_scrub_ugc.mp4
    python creatives/upload.py ~/Desktop/banner.jpg --type image --ad-id 120215998064080350

The script:
1. Creates the 'creatives' storage bucket if it does not exist yet.
2. Uploads the file to  creatives/{brand_id}/{creative_id}/{filename}
3. Inserts a row into the `creatives` table.
4. Prints the creative_id so you can reference it when tagging.

File-type is inferred from the extension if --type is not supplied:
  .mp4 / .mov / .avi / .mkv / .webm  → video
  .jpg / .jpeg / .png / .webp / .gif  → image
  (anything else requires --type explicitly)
"""
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

BUCKET = "creatives"

VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}


def _infer_file_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    return ""


def _ensure_bucket(sb) -> None:
    existing = [b.name for b in sb.storage.list_buckets()]
    if BUCKET not in existing:
        sb.storage.create_bucket(BUCKET, options={"public": False})
        print(f"  Created storage bucket '{BUCKET}'")


def upload_creative(
    file_path: str,
    file_type: str | None = None,
    ad_id: str | None = None,
) -> str:
    """
    Uploads a creative file to Supabase Storage and inserts a creatives row.
    Returns the new creative_id (uuid string).
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    sb = create_client(url, key)

    brands = sb.table("brands").select("id").execute().data
    if not brands:
        print("No brands found. Run seed_connections.py first.")
        sys.exit(1)
    brand_id = brands[0]["id"]

    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    inferred = _infer_file_type(path)
    if file_type:
        if file_type not in ("video", "image", "carousel"):
            print("--type must be one of: video, image, carousel")
            sys.exit(1)
    else:
        if not inferred:
            print(
                f"Cannot infer file type from extension '{path.suffix}'. "
                "Pass --type video|image|carousel explicitly."
            )
            sys.exit(1)
        file_type = inferred

    creative_id = str(uuid.uuid4())
    storage_path = f"{brand_id}/{creative_id}/{path.name}"
    mime_type, _ = mimetypes.guess_type(str(path))

    print(f"Uploading {path.name} ({file_type}) …")
    _ensure_bucket(sb)

    with open(path, "rb") as f:
        sb.storage.from_(BUCKET).upload(
            path=storage_path,
            file=f,
            file_options={"content-type": mime_type or "application/octet-stream"},
        )

    # Signed URL valid for 10 years — effectively permanent for internal use
    signed = sb.storage.from_(BUCKET).create_signed_url(storage_path, expires_in=315_360_000)
    file_url = signed["signedURL"]

    sb.table("creatives").insert({
        "id":        creative_id,
        "brand_id":  brand_id,
        "file_url":  file_url,
        "file_type": file_type,
        "ad_id":     ad_id,
    }).execute()

    print(f"  creative_id : {creative_id}")
    print(f"  storage path: {BUCKET}/{storage_path}")
    print(f"  file_type   : {file_type}")
    if ad_id:
        print(f"  ad_id       : {ad_id}")
    print("Done.")
    return creative_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a creative to Supabase Storage.")
    parser.add_argument("file_path", help="Local path to the video or image file.")
    parser.add_argument(
        "--type", dest="file_type", choices=["video", "image", "carousel"],
        help="Override inferred file type.",
    )
    parser.add_argument(
        "--ad-id", dest="ad_id", default=None,
        help="Meta ad_id to link this creative to (optional).",
    )
    args = parser.parse_args()
    upload_creative(args.file_path, args.file_type, args.ad_id)
