#!/usr/bin/env python3
"""
Set xmpDM:good in XMP sidecar files alongside Nikon NEF files.
Enables photo selection labels compatible with Lightroom.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_XMPDM_NS = "http://ns.adobe.com/xmp/1.0/DynamicMedia/"

_XMP_NEW = """\
<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 7.0-c000 1.000000, 0000/00/00-00:00:00        ">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmpDM="{ns}"
   xmpDM:good="{value}">
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end='w'?>"""


def _update_content(content: str, value: str | None) -> str:
    has_attr = bool(re.search(r'xmpDM:good\s*=', content))
    has_elem = bool(re.search(r'<xmpDM:good>', content))

    if value is None:
        content = re.sub(r'[ \t]*xmpDM:good\s*=\s*(?:"[^"]*"|\'[^\']*\')\n?', '', content)
        content = re.sub(r'[ \t]*<xmpDM:good>[^<]*</xmpDM:good>\n?', '', content)
    elif has_attr:
        content = re.sub(r'xmpDM:good\s*=\s*"[^"]*"', f'xmpDM:good="{value}"', content)
        content = re.sub(r"xmpDM:good\s*=\s*'[^']*'", f'xmpDM:good="{value}"', content)
    elif has_elem:
        content = re.sub(
            r'<xmpDM:good>[^<]*</xmpDM:good>',
            f'<xmpDM:good>{value}</xmpDM:good>',
            content,
        )
    else:
        ns_decl = '' if 'xmlns:xmpDM=' in content else f'\n    xmlns:xmpDM="{_XMPDM_NS}"'

        def _insert(m: re.Match) -> str:
            return f'{m.group(1)}{ns_decl}\n   xmpDM:good="{value}">'

        content = re.sub(
            r'(<rdf:Description\b[^>]*?)(>)',
            _insert, content, count=1, flags=re.DOTALL,
        )

    return content


def set_label(nef_path: "Path | str", accepted: "bool | None") -> None:
    """
    Write xmpDM:good to the XMP sidecar of a NEF file.

    accepted=True   -> xmpDM:good="True"  (採用)
    accepted=False  -> xmpDM:good="False" (不採用)
    accepted=None   -> attribute removed   (評価なし)
    """
    nef_path = Path(nef_path)
    xmp_path = nef_path.with_suffix('.xmp')
    value = None if accepted is None else ('True' if accepted else 'False')

    if not xmp_path.exists():
        if value is None:
            return
        xmp_path.write_text(
            _XMP_NEW.format(ns=_XMPDM_NS, value=value), encoding='utf-8',
        )
        return

    content = xmp_path.read_text(encoding='utf-8')
    xmp_path.write_text(_update_content(content, value), encoding='utf-8')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print(f'Usage: {sys.argv[0]} <nef_path> <True|False|None>', file=sys.stderr)
        sys.exit(1)
    arg = sys.argv[2]
    set_label(sys.argv[1], None if arg == 'None' else arg == 'True')
