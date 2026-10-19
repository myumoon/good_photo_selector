"""Read embedded NEF previews and capture times without writing beside photos."""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from PIL import Image, ImageOps

_TAG_SUBIFDS = 330
_TAG_JPEG_OFFSET = 513
_TAG_JPEG_LENGTH = 514
_TAG_EXIF_IFD = 0x8769
_TAG_DATETIME_ORIGINAL = 36867
_TAG_SUBSEC_TIME_ORIGINAL = 37521
_INT_TYPES = {1: ("B", 1), 3: ("H", 2), 4: ("I", 4), 13: ("I", 4)}


def _read(file_obj: BinaryIO, offset: int, size: int) -> bytes:
    file_obj.seek(offset)
    data = file_obj.read(size)
    if len(data) != size:
        raise struct.error("short read")
    return data


def _read_ifd(file_obj: BinaryIO, offset: int, byte_order: str) -> dict[int, list[int]]:
    (entry_count,) = struct.unpack(byte_order + "H", _read(file_obj, offset, 2))
    entries = _read(file_obj, offset + 2, entry_count * 12)
    tags: dict[int, list[int]] = {}
    for index in range(entry_count):
        tag, value_type, count, raw_value = struct.unpack_from(
            byte_order + "HHI4s", entries, index * 12,
        )
        if value_type not in _INT_TYPES or count == 0 or count > 64:
            continue
        value_format, value_size = _INT_TYPES[value_type]
        raw = raw_value if value_size * count <= 4 else _read(
            file_obj, struct.unpack(byte_order + "I", raw_value)[0], value_size * count,
        )
        tags[tag] = list(struct.unpack_from(f"{byte_order}{count}{value_format}", raw))
    return tags


def extract_embedded_jpeg(path: Path) -> bytes | None:
    """Return the largest JPEG in IFD0 or one of its SubIFDs, if present."""
    try:
        with Path(path).open("rb") as file_obj:
            header = file_obj.read(8)
            if len(header) < 8 or header[:2] not in (b"II", b"MM"):
                return None
            byte_order = "<" if header[:2] == b"II" else ">"
            try:
                magic, ifd0_offset = struct.unpack(byte_order + "HI", header[2:])
                if magic != 42:
                    return None
                root = _read_ifd(file_obj, ifd0_offset, byte_order)
                ifds = [root]
                for offset in root.get(_TAG_SUBIFDS, []):
                    try:
                        ifds.append(_read_ifd(file_obj, offset, byte_order))
                    except (OSError, struct.error):
                        continue
                spans = [
                    (ifd[_TAG_JPEG_OFFSET][0], ifd[_TAG_JPEG_LENGTH][0])
                    for ifd in ifds
                    if _TAG_JPEG_OFFSET in ifd and _TAG_JPEG_LENGTH in ifd
                ]
            except (OSError, struct.error):
                return None

            for start, length in sorted(spans, key=lambda span: span[1], reverse=True):
                try:
                    jpeg = _read(file_obj, start, length)
                except (OSError, struct.error):
                    continue
                if jpeg.startswith(b"\xff\xd8"):
                    return jpeg
    except OSError:
        return None
    return None


def capture_time(path: Path) -> float | None:
    """Return ExifIFD DateTimeOriginal plus SubSecTimeOriginal as epoch seconds."""
    try:
        with Image.open(path) as image:
            exif_ifd = image.getexif().get_ifd(_TAG_EXIF_IFD)
            date_text = exif_ifd.get(_TAG_DATETIME_ORIGINAL)
            if not date_text:
                return None
            epoch = datetime.strptime(str(date_text), "%Y:%m:%d %H:%M:%S").timestamp()
            subseconds = exif_ifd.get(_TAG_SUBSEC_TIME_ORIGINAL)
            if subseconds not in (None, "", "-"):
                digits = str(subseconds).strip()
                if digits.isdigit():
                    epoch += float("0." + digits)
            return epoch
    except (OSError, ValueError, TypeError, KeyError, AttributeError, struct.error):
        return None


def _exiftool_preview(path: Path) -> bytes | None:
    executable = shutil.which("exiftool")
    if executable is None:
        print(f"warning: no embedded JPEG and exiftool is unavailable: {path.name}", file=sys.stderr)
        return None
    try:
        result = subprocess.run(
            [executable, "-b", "-PreviewImage", str(path)],
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"warning: exiftool preview failed for {path.name}: {exc}", file=sys.stderr)
        return None
    if result.returncode != 0 or not result.stdout or not result.stdout.startswith(b"\xff\xd8"):
        print(f"warning: exiftool found no usable preview: {path.name}", file=sys.stderr)
        return None
    return result.stdout


def make_preview(nef: Path, out_jpg: Path, long_edge: int) -> Path | None:
    """Extract and resize one NEF preview, returning None after a per-file warning."""
    if long_edge <= 0:
        raise ValueError("long_edge must be a positive integer")
    jpeg = extract_embedded_jpeg(nef)
    if jpeg is None:
        jpeg = _exiftool_preview(Path(nef))
    if jpeg is None:
        return None
    try:
        with Image.open(BytesIO(jpeg)) as embedded:
            preview = ImageOps.exif_transpose(embedded).convert("RGB")
            preview.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
            out_jpg = Path(out_jpg)
            out_jpg.parent.mkdir(parents=True, exist_ok=True)
            preview.save(out_jpg, format="JPEG", quality=90)
        return out_jpg
    except (OSError, ValueError, TypeError) as exc:
        print(f"warning: could not create preview for {Path(nef).name}: {exc}", file=sys.stderr)
        return None
