"""Quality-analysis interface reserved for the future T2 implementation."""

from __future__ import annotations

from pathlib import Path


# Contract: hints(previews: list[Path]) -> dict[Path, str]
def hints(previews: list[Path]) -> dict[Path, str]:
    return {}


# Contract: face_crops(preview: Path, out_dir: Path) -> list[Path]
def face_crops(preview: Path, out_dir: Path) -> list[Path]:
    return []
