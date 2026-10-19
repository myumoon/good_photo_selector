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
