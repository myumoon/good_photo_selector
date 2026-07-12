# GootPhotoSelector

Claude Code を使って Nikon NEF 写真を自動選別し、Lightroom 互換の XMP ラベルを付けるツール。

## 概要

同一シチュエーションで撮った複数枚の写真を Claude が評価し、表情・構図・ピントを基準に採用/不採用を判定。  
判定結果は XMP サイドカーファイル（`xmpDM:good`）として保存され、Lightroom でそのまま確認できる。

## 動作環境

- Windows 10/11 + WSL2
- Python 3.x（WSL 内）
- Claude Code（claude.ai Pro/Max プラン）
- Adobe Lightroom（結果確認用）

## セットアップ

### 1. 依存ツールのインストール

**WSL（推奨）**

```bash
bash bin/setup.sh
```

または手動で:

```bash
sudo apt install libimage-exiftool-perl imagemagick
```

> **Note**: ImageMagick (`convert`) がないと、JPEG プレビューが 6048×4024 のままClaudeに渡されトークンを大量消費します。インストール済みの場合は 1280px にリサイズして渡します。

**Windows（WSL を使わず直接実行する場合）**

- **exiftool**: [exiftool.org](https://exiftool.org/) から Windows 版をダウンロードし、`exiftool.exe` を PATH の通ったフォルダに配置する。
- **ImageMagick**: [imagemagick.org](https://imagemagick.org/script/download.php#windows) から Windows 版をインストールし、`convert.exe` が PATH に通っていることを確認する。

### 2. リポジトリをクローン・セットアップ

```bash
# クローン
git clone <repo-url>
cd GootPhotoSelector

# 「送る」メニューへの登録（Windows・初回のみ）
bin\setup_sendto.bat をダブルクリック
```

## 使い方

### 右クリックから起動（推奨）

**フォルダ指定モード** — フォルダ内の全 NEF を処理する:

1. エクスプローラーで NEF ファイルが入ったフォルダを右クリック
2. **送る → GootPhotoSelector**
3. WSL ターミナルが開き Claude が自動選別を実行
4. 完了後に `Selection complete: X accepted / Y rejected` と表示
5. Enter で閉じる

**ファイル指定モード** — 選んだファイルだけを処理する:

1. エクスプローラーで処理したい NEF ファイルを複数選択
2. 右クリック → **送る → GootPhotoSelector**
3. 以降は同じ

### Claude Code から直接実行

```
「/path/to/photos フォルダの写真を選別してください」
```

Claude Code が CLAUDE.md のワークフローに従って自動処理する。

## 選別基準

| 採用 | 不採用 |
|------|--------|
| 笑顔の写真 | ブレている写真 |
| カメラ目線 | 半目の写真 |
| 構図が良い | 人物メインで顔がボケている |

ライティングや被写体の傾きは Lightroom で調整可能なため評価対象外。

## 仕組み

```
NEF ファイル
  └─ exiftool で JPEG プレビューを抽出
       └─ Claude が視覚評価
            └─ src/set_label.py で XMP サイドカーに xmpDM:good を書き込み
                 └─ Lightroom で採用/不採用ラベルとして表示
```

## ファイル構成

```
GootPhotoSelector/
├── bin/
│   ├── good_photo_selector.bat   # 「送る」ショートカットのターゲット
│   ├── good_photo_selector.sh    # Claude Code 起動スクリプト
│   └── setup_sendto.bat          # 「送る」メニュー登録ツール
├── src/
│   └── set_label.py        # XMP サイドカー書き込みライブラリ
├── docs/
│   └── xmp_sample/         # 採用・不採用・評価なしの XMP サンプル
├── CLAUDE.md               # Claude Code 向けガイド
└── AGENTS.md               # AI エージェント向けガイド
```
