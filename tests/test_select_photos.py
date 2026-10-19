import json
from pathlib import Path
from subprocess import CompletedProcess

from PIL import Image


def _driver():
    import select_photos

    return select_photos


def _make_nefs(folder, names):
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names:
        path = folder / name
        path.write_bytes(b"synthetic NEF")
        paths.append(path)
    return paths


def _install_previews(monkeypatch, driver, tmp_path, paths, times=None):
    times = times or {}

    def make_preview(nef, out_jpg, _long_edge):
        out_jpg.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (48, 32), "slateblue").save(out_jpg, format="JPEG")
        return out_jpg

    monkeypatch.setattr(driver, "make_preview", make_preview)
    monkeypatch.setattr(driver, "capture_time", lambda path: times.get(path))
    monkeypatch.setattr(driver.shutil, "which", lambda name: "claude.cmd" if name == "claude" else None)


def _payload(args, tiles):
    schema = json.loads(args[args.index("--json-schema") + 1])
    if "ok" in schema.get("properties", {}).get("tiles", {}).get("items", {}).get("properties", {}):
        data = {"tiles": [{"tile": tile, "ok": value, "reason": "目の状態"} for tile, value in tiles]}
    else:
        data = {"tiles": [{"tile": tile, "label": value, "reason": "比較理由"} for tile, value in tiles]}
    return json.dumps({"structured_output": data, "result": "do not use this text"}, ensure_ascii=False)


def test_cluster_bursts_uses_supplied_capture_times_without_exiftool(tmp_path, monkeypatch):
    import cluster_bursts

    paths = [tmp_path / "DSC_2.NEF", tmp_path / "DSC_1.NEF"]
    monkeypatch.setattr(cluster_bursts, "_capture_times", lambda _paths: (_ for _ in ()).throw(AssertionError()))
    times = {paths[0]: 10.0, paths[1]: 10.5}

    assert cluster_bursts.cluster_bursts(paths, 1.0, times=times) == [[paths[0], paths[1]]]


def test_cluster_bursts_keeps_capture_time_lookup_when_times_are_omitted(tmp_path, monkeypatch):
    import cluster_bursts

    paths = [tmp_path / "DSC_1.NEF", tmp_path / "DSC_2.NEF"]
    calls = []
    monkeypatch.setattr(cluster_bursts, "_capture_times", lambda selected: calls.append(selected) or {paths[0]: 10.0})

    assert cluster_bursts.cluster_bursts(paths, 1.0) == [[paths[0]], [paths[1]]]
    assert calls == [paths]


def test_end_to_end_clusters_reviews_and_writes_only_xmp(monkeypatch, tmp_path, capsys):
    driver = _driver()
    photo_dir = tmp_path / "photos"
    paths = _make_nefs(photo_dir, ["DSC_0001.NEF", "DSC_0002.NEF"])
    times = {paths[0]: 100.0, paths[1]: 100.25}
    _install_previews(monkeypatch, driver, tmp_path, paths, times)
    prompts = []
    commands = []
    face_calls = []
    monkeypatch.setattr(driver.quality, "hints", lambda previews: {previews[0]: "sharp focus"})

    def run(args, input, **kwargs):
        prompts.append(input)
        commands.append(args)
        return CompletedProcess(args, 0, _payload(args, [(1, "reject"), (2, "none")]), "")

    monkeypatch.setattr(driver.subprocess, "run", run)
    monkeypatch.setattr(driver.quality, "face_crops", lambda preview, out_dir: face_calls.append(preview) or [])
    runtime = tmp_path / "runtime"

    def make_temp_dir(prefix):
        runtime.mkdir()
        return str(runtime)

    monkeypatch.setattr(driver.tempfile, "mkdtemp", make_temp_dir)
    assert driver.main([str(photo_dir)]) == 0

    output = capsys.readouterr().out
    assert "[1/2] DSC_0001.NEF → rejected" in output
    assert "[2/2] DSC_0002.NEF → accepted" in output
    assert "Selection complete: 1 accepted / 1 rejected" in output
    assert len(prompts) == 1
    assert all(path.name not in prompts[0] for path in paths)
    assert "Tile 1: sharp focus" in prompts[0]
    assert commands[0][commands[0].index("--allowedTools") + 1] == "Read"
    assert "--json-schema" in commands[0]
    assert len(face_calls) == 1
    assert "xmpDM:good=\"False\"" in paths[0].with_suffix(".xmp").read_text(encoding="utf-8")
    assert "xmpDM:good=\"True\"" in paths[1].with_suffix(".xmp").read_text(encoding="utf-8")
    assert {path.name for path in photo_dir.iterdir()} == {
        "DSC_0001.NEF", "DSC_0002.NEF", "DSC_0001.xmp", "DSC_0002.xmp",
    }
    assert not runtime.exists()


def test_end_to_end_accepts_explicit_nef_paths(monkeypatch, tmp_path, capsys):
    driver = _driver()
    photo_dir = tmp_path / "photos"
    paths = _make_nefs(photo_dir, ["DSC_0001.NEF", "DSC_0002.NEF"])
    times = {path: 100.0 for path in paths}
    _install_previews(monkeypatch, driver, tmp_path, paths, times)
    prompts = []

    def run(args, input, **kwargs):
        prompts.append(input)
        return CompletedProcess(args, 0, _payload(args, [(1, "reject"), (2, "none")]), "")

    monkeypatch.setattr(driver.subprocess, "run", run)

    assert driver.main([str(paths[1]), str(paths[0])]) == 0

    output = capsys.readouterr().out
    assert "[1/2] DSC_0002.NEF → accepted" in output
    assert "[2/2] DSC_0001.NEF → rejected" in output
    assert len(prompts) == 1


def test_dry_run_builds_sheets_without_claude_or_xmp(monkeypatch, tmp_path, capsys):
    driver = _driver()
    photo_dir = tmp_path / "photos"
    paths = _make_nefs(photo_dir, ["DSC_0020.NEF"])
    _install_previews(monkeypatch, driver, tmp_path, paths)
    monkeypatch.setattr(driver.subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError()))
    runtime = tmp_path / "runtime"

    def make_temp_dir(prefix):
        runtime.mkdir()
        return str(runtime)

    monkeypatch.setattr(driver.tempfile, "mkdtemp", make_temp_dir)

    assert driver.main([str(photo_dir), "--dry-run", "--keep-previews"]) == 0

    output = capsys.readouterr().out
    assert "Dry run" in output
    assert "sheet" in output.lower()
    assert "Previews retained" in output
    assert any(runtime.rglob("*.jpg"))
    assert runtime.exists()
    assert not paths[0].with_suffix(".xmp").exists()
    assert {path.name for path in photo_dir.iterdir()} == {"DSC_0020.NEF"}


def test_failed_burst_retries_once_and_stays_unrated(monkeypatch, tmp_path, capsys):
    driver = _driver()
    photo_dir = tmp_path / "photos"
    paths = _make_nefs(photo_dir, ["DSC_0030.NEF"])
    _install_previews(monkeypatch, driver, tmp_path, paths)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            return CompletedProcess(args, 1, "", "failed")
        return CompletedProcess(args, 0, json.dumps({"result": '{"tiles":[]}'}), "")

    monkeypatch.setattr(driver.subprocess, "run", run)
    assert driver.main([str(photo_dir)]) == 0

    assert len(calls) == 2
    assert "unrated" in capsys.readouterr().out
    assert not paths[0].with_suffix(".xmp").exists()


def test_timed_out_claude_call_retries_once(monkeypatch, tmp_path):
    driver = _driver()
    photo_dir = tmp_path / "photos"
    paths = _make_nefs(photo_dir, ["DSC_0035.NEF"])
    _install_previews(monkeypatch, driver, tmp_path, paths)
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise driver.subprocess.TimeoutExpired(args, 180)
        return CompletedProcess(args, 0, _payload(args, [(1, "accept")]), "")

    monkeypatch.setattr(driver.subprocess, "run", run)

    assert driver.main([str(photo_dir)]) == 0
    assert len(calls) == 2
    assert paths[0].with_suffix(".xmp").exists()


def test_face_check_can_reject_a_photo(monkeypatch, tmp_path):
    driver = _driver()
    photo_dir = tmp_path / "photos"
    paths = _make_nefs(photo_dir, ["DSC_0040.NEF"])
    _install_previews(monkeypatch, driver, tmp_path, paths)
    calls = []

    def face_crops(preview, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        crop = out_dir / "face.jpg"
        Image.new("RGB", (12, 12), "white").save(crop, format="JPEG")
        return [crop]

    def run(args, input, **kwargs):
        calls.append(input)
        tiles = [(1, False)] if len(calls) == 2 else [(1, "none")]
        return CompletedProcess(args, 0, _payload(args, tiles), "")

    monkeypatch.setattr(driver.quality, "face_crops", face_crops)
    monkeypatch.setattr(driver.subprocess, "run", run)

    assert driver.main([str(photo_dir)]) == 0

    assert len(calls) == 2
    assert "eyes" not in calls[1].lower()
    assert "xmpDM:good=\"False\"" in paths[0].with_suffix(".xmp").read_text(encoding="utf-8")


def test_duplicate_and_out_of_range_tiles_are_none():
    driver = _driver()
    decisions = driver._parse_review({
        "tiles": [
            {"tile": 1, "label": "accept", "reason": "一度目"},
            {"tile": 1, "label": "reject", "reason": "重複"},
            {"tile": 4, "label": "reject", "reason": "範囲外"},
        ],
    }, 3)

    assert decisions == {1: "none", 2: "none", 3: "none"}


def test_contact_sheets_split_and_keep_global_tile_numbers(tmp_path):
    driver = _driver()
    images = []
    for index in range(5):
        path = tmp_path / f"preview_{index}.jpg"
        Image.new("RGB", (20, 10), (index * 20, 0, 0)).save(path, format="JPEG")
        images.append(path)

    sheets = driver._make_sheets(images, tmp_path / "sheets", "burst-01", 2, 2, 32)

    assert [(start, end) for _path, start, end in sheets] == [(1, 2), (3, 4), (5, 5)]
    assert len(sheets) == 3


def test_contact_sheet_badge_overlays_image_and_three_tiles_use_tight_width(tmp_path):
    driver = _driver()
    images = []
    for index in range(3):
        path = tmp_path / f"wide_{index}.jpg"
        Image.new("RGB", (48, 24), (180, 40, 40)).save(path, format="JPEG")
        images.append(path)

    sheets = driver._make_sheets(images, tmp_path / "sheets", "burst-01", 12, 4, 64)

    with Image.open(sheets[0][0]) as sheet:
        assert sheet.size == (3 * 64, 64)
        red, green, blue = sheet.getpixel((5, 21))
    assert red > 230 and green > 230 and blue > 230


def test_all_contact_sheets_for_a_large_burst_use_one_claude_call(monkeypatch, tmp_path):
    driver = _driver()
    photo_dir = tmp_path / "photos"
    paths = _make_nefs(photo_dir, [f"DSC_{index:04d}.NEF" for index in range(10, 15)])
    times = {path: 100.0 + index * 0.1 for index, path in enumerate(paths)}
    _install_previews(monkeypatch, driver, tmp_path, paths, times)
    settings = driver._load_settings()
    settings.update({"tile_px": 32, "cols": 2, "max_tiles": 2})
    monkeypatch.setattr(driver, "_load_settings", lambda: settings)
    prompts = []

    def run(args, input, **kwargs):
        prompts.append(input)
        return CompletedProcess(args, 0, _payload(args, [(tile, "none") for tile in range(1, 6)]), "")

    monkeypatch.setattr(driver.subprocess, "run", run)

    assert driver.main([str(photo_dir)]) == 0

    assert len(prompts) == 1
    assert "(tiles 1-2)" in prompts[0]
    assert "(tiles 3-4)" in prompts[0]
    assert "(tiles 5-5)" in prompts[0]


def test_settings_read_model_cluster_and_sheet_values(monkeypatch, tmp_path):
    driver = _driver()
    settings = tmp_path / "settings"
    settings.mkdir()
    (settings / "config.ini").write_text(
        "[claude]\nmodel = sonnet\n[cluster]\nburst_gap_seconds = 1.25\n"
        "[sheet]\ntile_px = 320\ncols = 3\nmax_tiles = 8\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(driver, "_SETTINGS_DIR", settings)

    assert driver._load_settings() == {
        "model": "sonnet", "gap_seconds": 1.25, "tile_px": 320, "cols": 3, "max_tiles": 8,
    }


def test_cli_contract_requires_structured_output_and_read_tool():
    driver = _driver()
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "claude-cli.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    basic = next(item for item in contract["probes"] if item["id"] == "p.json-schema.basic")
    image_tool_trap = next(item for item in contract["silent_ignore"] if item["id"] == "p.read-image.allowedTools-empty")
    body = basic["response"]["body"]
    argv = driver._claude_argv("claude.cmd", "opus", {"type": "object"})

    assert body["structured_output"] == {"ok": True, "n": 3}
    assert image_tool_trap["responses_identical"] is True
    assert image_tool_trap["wrong_request"]["allowedTools"] == ""
    assert argv[argv.index("--allowedTools") + 1] == "Read"
    assert "--json-schema" in argv


def test_prompt_files_define_three_label_and_face_schemas():
    driver = _driver()
    prompt_dir = Path(driver.__file__).resolve().parent / "prompts"
    schema_dir = Path(driver.__file__).resolve().parent / "schemas"
    burst_prompt = (prompt_dir / "burst_review.md").read_text(encoding="utf-8")
    face_prompt = (prompt_dir / "face_check.md").read_text(encoding="utf-8")
    burst_schema = json.loads((schema_dir / "burst_review.schema.json").read_text(encoding="utf-8"))
    face_schema = json.loads((schema_dir / "face_check.schema.json").read_text(encoding="utf-8"))

    assert "reject" in burst_prompt and "none" in burst_prompt and "accept" in burst_prompt
    assert "40" in burst_prompt
    assert "{sheets}" in burst_prompt and "{count}" in burst_prompt and "{hints}" in burst_prompt
    assert "{sheets}" in face_prompt and "{count}" in face_prompt
    assert burst_schema["properties"]["tiles"]["items"]["properties"]["label"]["enum"] == ["accept", "reject", "none"]
    assert face_schema["properties"]["tiles"]["items"]["properties"]["ok"]["type"] == "boolean"
