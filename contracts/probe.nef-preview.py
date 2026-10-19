#!/usr/bin/env python3
"""NEF(Nikon RAW, TIFF 系)の内蔵 JPEG と EXIF 撮影時刻の在りかを実測する。

    python3 contracts/probe.nef-preview.py contracts/nef-preview.contract.json [NEF...]

Surfaces:
  - IFD0 のタグ 330(SubIFDs) → 各 SubIFD の 513/514(JPEGInterchangeFormat/Length)
  - Pillow `Image.open(nef).getexif()` の ExifIFD(0x8769) にある DateTimeOriginal(36867) / SubSecTimeOriginal(37521)
  - IFD0 の Orientation(274)
"""

import json
import struct
import sys
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

DEFAULT_NEFS = [".env/test/DSC_7989.NEF", ".env/test/DSC_8020.NEF"]
_INT_TYPES = {1: ("B", 1), 3: ("H", 2), 4: ("I", 4), 13: ("I", 4)}


def _read_ifd(f, offset, bo):
    f.seek(offset)
    (count,) = struct.unpack(bo + "H", f.read(2))
    entries = f.read(count * 12)
    tags = {}
    for i in range(count):
        tag, typ, n, raw = struct.unpack_from(bo + "HHI4s", entries, i * 12)
        if typ not in _INT_TYPES or n == 0 or n > 64:
            continue
        fmt, size = _INT_TYPES[typ]
        if size * n <= 4:
            buf = raw
        else:
            f.seek(struct.unpack(bo + "I", raw)[0])
            buf = f.read(size * n)
        tags[tag] = list(struct.unpack_from(f"{bo}{n}{fmt}", buf))
    return tags


def subifd_jpegs(path):
    with open(path, "rb") as f:
        head = f.read(8)
        bo = "<" if head[:2] == b"II" else ">"
        magic, ifd0 = struct.unpack(bo + "HI", head[2:])
        root = _read_ifd(f, ifd0, bo)
        out = {"byte_order": head[:2].decode(), "magic": magic, "ifd0_orientation": root.get(274),
               "subifd_offsets": root.get(330, []), "subifds": []}
        for off in root.get(330, []):
            ifd = _read_ifd(f, off, bo)
            entry = {"offset": off, "has_513_514": 513 in ifd and 514 in ifd}
            if entry["has_513_514"]:
                f.seek(ifd[513][0])
                blob = f.read(ifd[514][0])
                entry["jpeg_length"] = ifd[514][0]
                entry["starts_with_ffd8"] = blob[:2] == b"\xff\xd8"
                entry["size"] = list(Image.open(BytesIO(blob)).size)
            out["subifds"].append(entry)
        return out


def exif_times(path):
    ex = Image.open(path).getexif()
    exif_ifd = ex.get_ifd(0x8769)
    return {
        "exif_ifd.DateTimeOriginal(36867)": exif_ifd.get(36867),
        "exif_ifd.SubSecTimeOriginal(37521)": exif_ifd.get(37521),
        "ifd0.DateTime(306)": ex.get(306),
        "ifd0.Orientation(274)": ex.get(274),
        "ifd0.get(36867)": ex.get(36867),
        "ifd0.get_ifd(330)": dict(ex.get_ifd(330)),
    }


def main(argv):
    if len(argv) < 2:
        print("usage: probe.nef-preview.py <output-contract.json> [NEF...]", file=sys.stderr)
        return 2
    nefs = argv[2:] or DEFAULT_NEFS
    probes, silent = [], []
    for nef in nefs:
        p = Path(nef)
        probes.append({"id": f"nef.subifd.{p.stem}", "surface": "NEF SubIFD JPEG (330 -> 513/514)",
                       "arguments_exercised": True,
                       "request": {"path": p.name, "file_size": p.stat().st_size},
                       "response": subifd_jpegs(p)})
        probes.append({"id": f"nef.exif.{p.stem}", "surface": "NEF EXIF via Pillow getexif()",
                       "arguments_exercised": True,
                       "request": {"path": p.name}, "response": exif_times(p)})
    first = Path(nefs[0])
    t = exif_times(first)
    silent.append({
        "id": "nef.exif.datetimeoriginal-toplevel",
        "surface": "NEF EXIF via Pillow getexif()",
        "correct_request": {"call": "getexif().get_ifd(0x8769).get(36867)"},
        "wrong_request": {"call": "getexif().get(36867)"},
        "responses_identical": t["exif_ifd.DateTimeOriginal(36867)"] == t["ifd0.get(36867)"],
        "impact": "DateTimeOriginal は ExifIFD 側にある。IFD0 直下を引くと None になり連写クラスタが全崩れする",
        "guard": "撮影時刻は get_ifd(0x8769) から読む。None なら mtime ではなくファイル名順へ退避",
    })
    silent.append({
        "id": "nef.subifd.pillow-get_ifd-330",
        "surface": "NEF SubIFD JPEG (330 -> 513/514)",
        "correct_request": {"call": "struct で IFD0 の 330 を辿る"},
        "wrong_request": {"call": "getexif().get_ifd(330)"},
        "responses_identical": False if t["ifd0.get_ifd(330)"] == {} else True,
        "impact": "Pillow の get_ifd(330) は空 dict を返すので、内蔵 JPEG が見つからない",
        "guard": "SubIFD は struct で自前パースする(contracts の subifds を参照)",
    })
    out = {"schema_version": 1, "name": "nef-preview", "captured_at": _utc_now(),
           "target": {"kind": "file", "identity": "Nikon NEF (Z 系, .env/test) を Pillow 9 + struct で読む", "base": None},
           "probes": probes, "silent_ignore": silent}
    Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "DONE", "contract_file": argv[1], "probes": len(probes),
                      "silent_ignore_checks": len(silent),
                      "subifds": [pr["response"]["subifds"] for pr in probes if pr["surface"].startswith("NEF SubIFD")][0]},
                     ensure_ascii=False))
    return 0


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
