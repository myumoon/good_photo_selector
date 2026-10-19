#!/usr/bin/env python3
"""`claude -p` の構造化出力(--json-schema)と画像 Read の契約を実測する。

    python3 contracts/probe.claude-cli.py contracts/claude-cli.contract.json

Surfaces:
  - `claude -p --output-format json --json-schema <schema> --allowedTools "" --model <m>`
    (stdin でプロンプト、stdout に JSON 1 件)
  - 同上 + `--allowedTools Read` で番号付きコンタクトシート画像を読ませる
"""

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

MODEL = "sonnet"
TIMEOUT = 180
CMD_SHIM_UNSAFE_CHARS = set("%&|<>^")


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_claude(prompt, schema=None, allowed_tools="", cwd=None):
    exe = shutil.which("claude")
    argv = [exe, "-p", "--output-format", "json", "--allowedTools", allowed_tools, "--model", MODEL]
    if schema is not None:
        argv += ["--json-schema", json.dumps(schema)]
    if Path(exe).suffix.lower() in {".cmd", ".bat"} and any(
        any(ch in a for ch in CMD_SHIM_UNSAFE_CHARS) for a in argv[1:]
    ):
        return {"exit_code": None, "stderr": "unsafe_cmd_arg", "body_text": ""}
    done = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=TIMEOUT, cwd=cwd)
    resp = {"exit_code": done.returncode, "stderr": done.stderr[-500:]}
    try:
        resp["body"] = json.loads(done.stdout)
    except json.JSONDecodeError:
        resp["body_text"] = done.stdout[-2000:]
    return resp, argv[1:]


def strip_volatile(resp):
    body = resp.get("body")
    if not isinstance(body, dict):
        return resp
    keep = {k: body.get(k) for k in ("type", "subtype", "is_error", "structured_output")}
    keep["has_result"] = "result" in body
    return {"exit_code": resp.get("exit_code"), "body": keep}


def make_sheet(path):
    """3 タイル(赤・緑・青)に 1〜3 の番号バッジを描いたコンタクトシート。"""
    cell = 200
    img = Image.new("RGB", (cell * 3, cell), "white")
    d = ImageDraw.Draw(img)
    for i, color in enumerate(["red", "green", "blue"]):
        x = i * cell
        d.rectangle([x + 10, 10, x + cell - 10, cell - 10], fill=color)
        d.rectangle([x + 14, 14, x + 50, 50], fill="white")
        d.text((x + 24, 22), str(i + 1), fill="black")
    img.save(path, "JPEG", quality=85)


def main(argv):
    if len(argv) != 2:
        print("usage: probe.claude-cli.py <output-contract.json>", file=sys.stderr)
        return 2
    probes, silent = [], []

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "n": {"type": "integer"}},
              "required": ["ok", "n"], "additionalProperties": False}
    prompt = "Reply with ok=true and n=3. No tools."

    # surface 1: structured output
    resp_ok, argv_ok = run_claude(prompt, schema)
    probes.append({"id": "p.json-schema.basic", "surface": "claude -p --json-schema",
                   "arguments_exercised": True,
                   "request": {"argv": argv_ok, "stdin": prompt}, "response": resp_ok})
    # wrong form: schema written into the prompt instead of --json-schema
    resp_wrong, argv_wrong = run_claude(prompt + " Answer as JSON matching " + json.dumps(schema), None)
    probes.append({"id": "p.json-schema.in-prompt", "surface": "claude -p --json-schema",
                   "arguments_exercised": True,
                   "request": {"argv": argv_wrong, "stdin": prompt + " (schema in prompt)"},
                   "response": resp_wrong})
    silent.append({
        "id": "p.json-schema.schema-in-prompt",
        "surface": "claude -p --json-schema",
        "correct_request": {"argv": argv_ok},
        "wrong_request": {"argv": argv_wrong},
        "responses_identical": strip_volatile(resp_ok) == strip_volatile(resp_wrong),
        "impact": "schema をプロンプト文に書いただけでは structured_output が付かず、result の自由文を自前でパースすることになる",
        "guard": "必ず --json-schema フラグで渡し、body.structured_output を読む。result は読まない",
    })

    # surface 2: Read an image (contact sheet) and answer by tile number
    tmp = Path(tempfile.mkdtemp(prefix="gps-probe-"))
    sheet = tmp / "sheet.jpg"
    make_sheet(sheet)
    schema2 = {"type": "object", "properties": {"red_tile": {"type": "integer"}, "blue_tile": {"type": "integer"}},
               "required": ["red_tile", "blue_tile"], "additionalProperties": False}
    prompt2 = (f"Use the Read tool to open the image at {sheet.as_posix()}. It is a contact sheet of 3 tiles; "
               "each tile has a white badge with its number (1-3) at the top-left. "
               "Return the tile number that is red and the one that is blue.")
    resp_img, argv_img = run_claude(prompt2, schema2, allowed_tools="Read", cwd=str(tmp))
    probes.append({"id": "p.read-image.sheet", "surface": "claude -p --allowedTools Read (image)",
                   "arguments_exercised": True,
                   "request": {"argv": argv_img, "stdin": prompt2, "sheet": "3 tiles red/green/blue, badges 1..3"},
                   "response": resp_img})
    # wrong form: Read not allowed -> cannot see the image
    resp_noread, argv_noread = run_claude(prompt2, schema2, allowed_tools="", cwd=str(tmp))
    probes.append({"id": "p.read-image.no-read-tool", "surface": "claude -p --allowedTools Read (image)",
                   "arguments_exercised": True,
                   "request": {"argv": argv_noread, "stdin": prompt2}, "response": resp_noread})
    silent.append({
        "id": "p.read-image.allowedTools-empty",
        "surface": "claude -p --allowedTools Read (image)",
        "correct_request": {"allowedTools": "Read"},
        "wrong_request": {"allowedTools": ""},
        "responses_identical": strip_volatile(resp_img) == strip_volatile(resp_noread),
        "impact": "--allowedTools に Read が無いと画像を見ずに回答(推測)が返る。exit 0 のまま誤判定になる",
        "guard": "画像を渡す呼び出しは必ず --allowedTools Read。structured_output が期待値と違えば警告",
    })

    out = {"schema_version": 1, "name": "claude-cli", "captured_at": _utc_now(),
           "target": {"kind": "cli", "identity": f"claude -p (Claude Code CLI, --model {MODEL})", "base": None},
           "probes": probes, "silent_ignore": silent}
    Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "DONE", "contract_file": argv[1], "probes": len(probes),
                      "silent_ignore_checks": len(silent),
                      "basic": strip_volatile(resp_ok), "image": strip_volatile(resp_img)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
