import json
import struct
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image


def _module():
    import nef_preview

    return nef_preview


def _entry(order, tag, value, count=1):
    return struct.pack(order + "HHI4s", tag, 4, count, struct.pack(order + "I", value))


def _ifd(order, entries):
    return struct.pack(order + "H", len(entries)) + b"".join(entries) + struct.pack(order + "I", 0)


def _synthetic_nef(order):
    small = b"\xff\xd8small\xff\xd9"
    large = b"\xff\xd8larger-preview\xff\xd9"
    ifd0_offset = 8
    offsets_offset = 26
    small_ifd_offset = 34
    large_ifd_offset = 64
    small_jpeg_offset = 94
    large_jpeg_offset = small_jpeg_offset + len(small)
    header = (b"II" if order == "<" else b"MM") + struct.pack(order + "HI", 42, ifd0_offset)
    root = _ifd(order, [_entry(order, 330, offsets_offset, 2)])
    offset_array = struct.pack(order + "II", small_ifd_offset, large_ifd_offset)
    small_ifd = _ifd(order, [
        _entry(order, 513, small_jpeg_offset),
        _entry(order, 514, len(small)),
    ])
    large_ifd = _ifd(order, [
        _entry(order, 513, large_jpeg_offset),
        _entry(order, 514, len(large)),
    ])
    return header + root + offset_array + small_ifd + large_ifd + small + large, large


@pytest.mark.parametrize("order", ["<", ">"])
def test_extracts_largest_subifd_jpeg_in_both_byte_orders(tmp_path, order):
    module = _module()
    content, expected = _synthetic_nef(order)
    path = tmp_path / "sample.NEF"
    path.write_bytes(content)

    assert module.extract_embedded_jpeg(path) == expected


def test_returns_none_for_tiff_without_embedded_jpeg(tmp_path):
    module = _module()
    path = tmp_path / "empty.NEF"
    path.write_bytes(b"II" + struct.pack("<HI", 42, 8) + _ifd("<", []))

    assert module.extract_embedded_jpeg(path) is None


def test_capture_time_reads_exif_ifd_and_subseconds(monkeypatch, tmp_path):
    module = _module()

    class Exif(dict):
        def get_ifd(self, tag):
            assert tag == 0x8769
            return {36867: "2026:07:11 13:49:28", 37521: "13"}

    class FakeImage:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getexif(self):
            return Exif({306: "2026:07:11 13:49:28", 36867: None})

    monkeypatch.setattr(module.Image, "open", lambda _path: FakeImage())
    expected = datetime.strptime("2026:07:11 13:49:28", "%Y:%m:%d %H:%M:%S").timestamp() + 0.13

    assert module.capture_time(tmp_path / "sample.NEF") == pytest.approx(expected)


def test_falls_back_to_exiftool_only_when_embedded_jpeg_is_absent(monkeypatch, tmp_path):
    module = _module()
    path = tmp_path / "missing-preview.NEF"
    path.write_bytes(b"not a tiff")
    jpeg_path = tmp_path / "fallback.jpg"
    Image.new("RGB", (128, 64), "navy").save(jpeg_path, format="JPEG")
    jpeg = jpeg_path.read_bytes()
    commands = []

    monkeypatch.setattr(module.shutil, "which", lambda name: "exiftool.exe" if name == "exiftool" else None)

    def fake_run(args, **kwargs):
        commands.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout=jpeg)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    out = tmp_path / "preview.jpg"

    assert module.make_preview(path, out, 32) == out
    with Image.open(out) as preview:
        assert preview.size == (32, 16)
    assert commands[0][0][:3] == ["exiftool.exe", "-b", "-PreviewImage"]


def test_make_preview_applies_nef_orientation_without_jpeg_exif(monkeypatch, tmp_path):
    module = _module()
    nef = tmp_path / "portrait.NEF"
    Image.new("RGB", (40, 20), "red").save(nef, format="TIFF", tiffinfo={274: 6})
    embedded_path = tmp_path / "embedded.jpg"
    Image.new("RGB", (40, 20), "blue").save(embedded_path, format="JPEG")
    monkeypatch.setattr(module, "extract_embedded_jpeg", lambda _path: embedded_path.read_bytes())
    out = tmp_path / "preview.jpg"

    assert module.make_preview(nef, out, 40) == out
    with Image.open(out) as preview:
        assert preview.width < preview.height


def test_warns_and_skips_when_no_embedded_jpeg_or_exiftool(monkeypatch, capsys, tmp_path):
    module = _module()
    path = tmp_path / "missing-preview.NEF"
    path.write_bytes(b"not a tiff")
    monkeypatch.setattr(module.shutil, "which", lambda _name: None)

    assert module.make_preview(path, tmp_path / "preview.jpg", 32) is None
    assert "exiftool" in capsys.readouterr().err


def test_contract_records_subifd_and_exififd_traps():
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "nef-preview.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    traps = {item["id"]: item for item in contract["silent_ignore"]}

    assert traps["nef.exif.datetimeoriginal-toplevel"]["responses_identical"] is True
    assert traps["nef.subifd.pillow-get_ifd-330"]["responses_identical"] is False
    assert "get_ifd(0x8769)" in traps["nef.exif.datetimeoriginal-toplevel"]["correct_request"]["call"]
    assert "struct" in traps["nef.subifd.pillow-get_ifd-330"]["correct_request"]["call"]
