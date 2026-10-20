# 環境の落とし穴(この worktree)

- シェルは Windows Git Bash。`python` は Anaconda の 3.9.12。`python3` は存在しないか別物なので、検証は `python -m pytest` で呼ぶ。
- Python 3.9 なので `match` / `tomllib` / 実行時の `int | None` は使えない。`from __future__ import annotations` を各モジュール先頭に置けば注釈内の `X | None` は可。
- exiftool は Windows 側に無い。テストで exiftool を呼ぶ経路は `shutil.which` を monkeypatch してモックする。
- `convert` は Windows の `convert.exe`(ファイルシステム変換ツール)であり ImageMagick ではない。使わない。
- `claude` は Windows では `claude.cmd`(npm シム)。テストでは `subprocess.run` を monkeypatch し、実 CLI を呼ばない。
- 文字コードは cp932 の罠がある。ファイル読み書きは必ず `encoding="utf-8"`、subprocess は `text=True, encoding="utf-8", errors="replace"`。
- `.env/` はディレクトリ(gitignore 対象、30MB の NEF が入っている)。テストから参照しない。
- `settings/*.ini` は gitignore 対象。コミットするのは `settings/config.ini.example` だけ。
- pytest は `tests/conftest.py` で `sys.path.insert(0, "<repo>/src")` してから `import select_photos` する。
- PowerShell では `tail` が Git の `tail.exe` に解決され CreateFileMapping エラーで落ちることがある。末尾抽出は `Select-Object -Last N` を使う。
- PowerShell の `python` は pyenv 3.11.9 で pytest が無い。pytest 実行は事前ブリーフどおり Git Bash の Python 環境を使う。
- この実行環境では Git Bash 自体も `CreateFileMapping ... Win32 error 5` で起動できない。PowerShell から利用可能な pytest 付き Python を探す。
- pytest の既定一時領域 `C:\Users\neko\AppData\Local\Temp` は sandbox が拒否する。実行時の `TEMP` と `TMP` を worktree 内へ向ける。
- 実環境の Pillow 9.0.1 では `Image.Resampling` が未提供。縮小処理は `Image.LANCZOS` fallback も用意する。
PowerShell task shell: Git Bash may fail to start with CreateFileMapping Win32 error 5; use PowerShell. Default pytest temp under LocalAppData may be blocked, so set TEMP/TMP to a workspace .tmp; the pyenv Python may lack pytest while Anaconda Python has it.
- When prepending Anaconda for a launcher check, retain the existing PATH; dropping it can hide Anaconda DLL directories and make Pillow's `_imaging` import fail.
- PowerShell `Remove-Item` can throw `NullReferenceException` on a directory junction; after verifying the in-worktree reparse point, `[System.IO.Directory]::Delete(path, $false)` removes the link without traversing its target.
