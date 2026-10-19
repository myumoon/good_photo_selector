#!/usr/bin/env python3
"""Review NEF bursts with numbered contact sheets and write Lightroom XMP labels."""

from __future__ import annotations

import argparse
import configparser
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

import cluster_bursts
import quality
from nef_preview import capture_time, make_preview
from set_label import set_label

_ROOT = Path(__file__).resolve().parent.parent
_SETTINGS_DIR = _ROOT / "settings"
_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
_DEFAULT_SETTINGS = {
    "model": "opus",
    "gap_seconds": 2.0,
    "tile_px": 512,
    "cols": 4,
    "max_tiles": 12,
}
_SETTING_SOURCES = {
    "model": ("claude", "model", str),
    "gap_seconds": ("cluster", "burst_gap_seconds", float),
    "tile_px": ("sheet", "tile_px", int),
    "cols": ("sheet", "cols", int),
    "max_tiles": ("sheet", "max_tiles", int),
}
_CLAUDE_TIMEOUT_SECONDS = 180


def _load_settings() -> dict[str, Any]:
    settings = dict(_DEFAULT_SETTINGS)
    found = set()
    for ini_path in sorted(_SETTINGS_DIR.glob("*.ini")):
        parser = configparser.ConfigParser()
        try:
            parser.read(ini_path, encoding="utf-8")
        except (OSError, configparser.Error):
            continue
        for key, (section, option, cast) in _SETTING_SOURCES.items():
            if key in found or not parser.has_option(section, option):
                continue
            try:
                value = cast(parser.get(section, option))
                if isinstance(value, str):
                    if not value.strip():
                        continue
                    value = value.strip()
                elif value <= 0:
                    continue
            except (ValueError, configparser.Error):
                continue
            settings[key] = value
            found.add(key)
    return settings


def _claude_argv(executable: str, model: str, schema: dict[str, Any]) -> list[str]:
    return [
        executable,
        "-p",
        "--output-format",
        "json",
        "--allowedTools",
        "Read",
        "--model",
        model,
        "--json-schema",
        json.dumps(schema),
    ]


def _call_claude(prompt: str, schema: dict[str, Any], model: str) -> dict[str, Any]:
    for attempt in range(2):
        try:
            executable = shutil.which("claude")
            if executable is None:
                raise RuntimeError("claude CLI was not found")
            result = subprocess.run(
                _claude_argv(executable, model, schema),
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_CLAUDE_TIMEOUT_SECONDS,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(f"claude exited with status {result.returncode}")
            payload = json.loads(result.stdout)
            structured = payload.get("structured_output") if isinstance(payload, dict) else None
            if not isinstance(structured, dict) or not isinstance(structured.get("tiles"), list):
                raise ValueError("claude response has no structured_output.tiles")
            return structured
        except Exception as exc:
            print(f"warning: Claude call {attempt + 1}/2 failed: {exc}", file=sys.stderr)
            if attempt == 1:
                raise RuntimeError("claude failed after one retry") from exc
    raise RuntimeError("claude failed")


def _parse_review(response: dict[str, Any], tile_count: int) -> dict[int, str]:
    decisions = {tile: "none" for tile in range(1, tile_count + 1)}
    seen = set()
    for item in response["tiles"]:
        if not isinstance(item, dict):
            continue
        tile = item.get("tile")
        if type(tile) is not int or tile < 1 or tile > tile_count:
            continue
        if tile in seen:
            decisions[tile] = "none"
            continue
        seen.add(tile)
        label = item.get("label")
        decisions[tile] = label if label in ("accept", "reject", "none") else "none"
    return decisions


def _parse_face_review(response: dict[str, Any], tile_count: int) -> dict[int, bool | None]:
    decisions = {tile: None for tile in range(1, tile_count + 1)}
    seen = set()
    for item in response["tiles"]:
        if not isinstance(item, dict):
            continue
        tile = item.get("tile")
        if type(tile) is not int or tile < 1 or tile > tile_count:
            continue
        if tile in seen:
            decisions[tile] = None
            continue
        seen.add(tile)
        value = item.get("ok")
        decisions[tile] = value if type(value) is bool else None
    return decisions


def _make_sheets(
    images: list[Path], out_dir: Path, prefix: str, max_tiles: int, cols: int, tile_px: int,
) -> list[tuple[Path, int, int]]:
    if max_tiles <= 0 or cols <= 0 or tile_px <= 0:
        raise ValueError("sheet dimensions and tile limit must be positive")
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets = []
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
    nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
    badge_size = max(1, tile_px // 8)
    badge_font = None
    for font_path in (
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "arialbd.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ):
        try:
            badge_font = ImageFont.truetype(font_path, max(1, badge_size * 3 // 4))
            break
        except OSError:
            pass
    for start_index in range(0, len(images), max_tiles):
        chunk = images[start_index:start_index + max_tiles]
        rows = int(math.ceil(len(chunk) / float(cols)))
        canvas_width = min(cols, len(chunk)) * tile_px
        canvas = Image.new("RGB", (canvas_width, rows * tile_px), "#303030")
        draw = ImageDraw.Draw(canvas)
        for offset, image_path in enumerate(chunk):
            with Image.open(image_path) as source:
                tile = source.convert("RGB")
                tile.thumbnail((tile_px, tile_px), resampling)
            x = (offset % cols) * tile_px
            y = (offset // cols) * tile_px
            image_x = x + (tile_px - tile.width) // 2
            image_y = y + (tile_px - tile.height) // 2
            canvas.paste(tile, (image_x, image_y))
            number = start_index + offset + 1
            text = str(number)
            if badge_font is None:
                small_size = max(1, badge_size // 4)
                badge = Image.new("RGB", (small_size, small_size), "white")
                ImageDraw.Draw(badge).text((0, 0), text, fill="black", font=ImageFont.load_default())
                badge = badge.resize((badge_size, badge_size), nearest)
                canvas.paste(badge, (image_x, image_y))
            else:
                badge_box = (
                    image_x,
                    image_y,
                    image_x + badge_size - 1,
                    image_y + badge_size - 1,
                )
                draw.rectangle(badge_box, fill="white")
                text_box = badge_font.getbbox(text)
                text_width = text_box[2] - text_box[0]
                text_height = text_box[3] - text_box[1]
                text_x = image_x + (badge_size - text_width) // 2 - text_box[0]
                text_y = image_y + (badge_size - text_height) // 2 - text_box[1]
                draw.text((text_x, text_y), text, fill="black", font=badge_font)
        sheet_path = out_dir / f"{prefix}-{len(sheets) + 1:02d}.jpg"
        canvas.save(sheet_path, format="JPEG", quality=90)
        first_tile = start_index + 1
        sheets.append((sheet_path, first_tile, first_tile + len(chunk) - 1))
    return sheets


def _format_sheets(sheets: list[tuple[Path, int, int]]) -> str:
    return "\n".join(f"{path} (tiles {first}-{last})" for path, first, last in sheets)


def _burst_prompt(
    sheets: list[tuple[Path, int, int]], count: int, burst_previews: list[Path],
    hints: dict[Path, str],
) -> str:
    hint_lines = []
    for tile, preview in enumerate(burst_previews, 1):
        hint = hints.get(preview)
        if hint:
            hint_lines.append(f"Tile {tile}: {str(hint).replace(chr(10), ' ').strip()}")
    template = (_PROMPT_DIR / "burst_review.md").read_text(encoding="utf-8")
    return template.format(
        sheets=_format_sheets(sheets),
        count=count,
        hints="\n".join(hint_lines) if hint_lines else "（なし）",
    )


def _face_prompt(sheets: list[tuple[Path, int, int]], count: int) -> str:
    template = (_PROMPT_DIR / "face_check.md").read_text(encoding="utf-8")
    return template.format(sheets=_format_sheets(sheets), count=count)


def _write_burst_labels(
    burst: list[Path], decisions: dict[int, str], statuses: dict[Path, str],
) -> None:
    for tile, nef in enumerate(burst, 1):
        label = decisions[tile]
        accepted = True if label == "accept" else False if label == "reject" else None
        try:
            set_label(nef, accepted)
        except OSError as exc:
            print(f"warning: could not write XMP for {nef.name}: {exc}", file=sys.stderr)
            statuses[nef] = "unrated"
            continue
        statuses[nef] = "accepted" if label == "accept" else "rejected" if label == "reject" else "unrated"


def _review_burst(
    burst: list[Path], burst_number: int, previews: dict[Path, Path],
    hints: dict[Path, str], settings: dict[str, Any], workspace: Path,
) -> dict[int, str]:
    burst_previews = [previews[nef] for nef in burst]
    sheets = _make_sheets(
        burst_previews,
        workspace / "sheets",
        f"burst-{burst_number:03d}",
        settings["max_tiles"],
        settings["cols"],
        settings["tile_px"],
    )
    schema = json.loads((_SCHEMA_DIR / "burst_review.schema.json").read_text(encoding="utf-8"))
    response = _call_claude(
        _burst_prompt(sheets, len(burst), burst_previews, hints), schema, settings["model"],
    )
    decisions = _parse_review(response, len(burst))

    face_images = []
    face_owners = []
    for tile, nef in enumerate(burst, 1):
        if decisions[tile] == "reject":
            continue
        try:
            crops = quality.face_crops(previews[nef], workspace / "faces" / f"burst-{burst_number:03d}" / f"tile-{tile:03d}")
        except Exception as exc:
            print(f"warning: face crop failed for {nef.name}: {exc}", file=sys.stderr)
            continue
        for crop in crops:
            face_images.append(Path(crop))
            face_owners.append(tile)

    if face_images:
        face_sheets = _make_sheets(
            face_images,
            workspace / "face-sheets",
            f"face-{burst_number:03d}",
            settings["max_tiles"],
            settings["cols"],
            settings["tile_px"],
        )
        face_schema = json.loads((_SCHEMA_DIR / "face_check.schema.json").read_text(encoding="utf-8"))
        face_response = _call_claude(
            _face_prompt(face_sheets, len(face_images)), face_schema, settings["model"],
        )
        face_decisions = _parse_face_review(face_response, len(face_images))
        for face_tile, ok in face_decisions.items():
            if ok is False:
                decisions[face_owners[face_tile - 1]] = "reject"

    remaining = [tile for tile, label in decisions.items() if label != "reject"]
    if len(remaining) == 1 and decisions[remaining[0]] == "none":
        decisions[remaining[0]] = "accept"
    return decisions


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review NEF bursts using numbered contact sheets.")
    parser.add_argument("sources", nargs="+", metavar="DIR|NEF")
    parser.add_argument("--model", help="Claude model name (overrides settings)")
    parser.add_argument("--dry-run", action="store_true", help="Build sheets without calling Claude or writing XMP")
    parser.add_argument("--keep-previews", action="store_true", help="Keep temporary previews and contact sheets")
    return parser


def main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    nefs = cluster_bursts._collect_nefs(args.sources)
    if not nefs:
        print("No NEF files found.", file=sys.stderr)
        return 1

    settings = _load_settings()
    if args.model:
        settings["model"] = args.model
    workspace = Path(tempfile.mkdtemp(prefix="good-photo-selector-"))
    statuses = {nef: "unrated" for nef in nefs}
    try:
        previews = {}
        capture_times = {}
        for index, nef in enumerate(nefs, 1):
            preview = make_preview(nef, workspace / "previews" / f"preview-{index:04d}.jpg", settings["tile_px"])
            if preview is None:
                continue
            previews[nef] = preview
            timestamp = capture_time(nef)
            if timestamp is not None:
                capture_times[nef] = timestamp

        preview_paths = list(previews.values())
        try:
            hints = quality.hints(preview_paths)
        except Exception as exc:
            print(f"warning: quality hints unavailable: {exc}", file=sys.stderr)
            hints = {}
        bursts = cluster_bursts.cluster_bursts(
            list(previews), settings["gap_seconds"], times=capture_times,
        )

        if args.dry_run:
            for burst_number, burst in enumerate(bursts, 1):
                burst_previews = [previews[nef] for nef in burst]
                sheets = _make_sheets(
                    burst_previews,
                    workspace / "sheets",
                    f"burst-{burst_number:03d}",
                    settings["max_tiles"],
                    settings["cols"],
                    settings["tile_px"],
                )
                print(f"Dry run: burst {burst_number} ({len(burst)} photos)")
                for sheet, first, last in sheets:
                    print(f"  sheet: {sheet} (tiles {first}-{last})")
            for nef in nefs:
                if nef not in previews:
                    print(f"Dry run: no preview for {nef.name}; would remain unrated")
            return 0

        for burst_number, burst in enumerate(bursts, 1):
            try:
                decisions = _review_burst(burst, burst_number, previews, hints, settings, workspace)
            except Exception as exc:
                names = ", ".join(nef.name for nef in burst)
                print(f"warning: burst {burst_number} ({names}) is unrated: {exc}", file=sys.stderr)
                continue
            _write_burst_labels(burst, decisions, statuses)

        for index, nef in enumerate(nefs, 1):
            if nef not in previews:
                print(f"warning: skipped {nef.name}; no preview available", file=sys.stderr)
            print(f"[{index}/{len(nefs)}] {nef.name} → {statuses[nef]}")
        accepted_count = sum(status == "accepted" for status in statuses.values())
        rejected_count = sum(status == "rejected" for status in statuses.values())
        print(f"Selection complete: {accepted_count} accepted / {rejected_count} rejected")
        return 0
    finally:
        if args.keep_previews:
            print(f"Previews retained: {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
