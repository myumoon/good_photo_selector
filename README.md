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
sudo apt install libimage-exiftool-perl python3-pil
```

Pillow は NEF 内蔵 JPEG の縮小とコンタクトシート生成に使います。exiftool は内蔵 JPEG が見つからない NEF のフォールバック用です。

**Windows（WSL を使わず直接実行する場合）**

- Python 3 と Pillow を用意する。exiftool は内蔵 JPEG がないファイルの読み込みに必要です。

### 2. リポジトリをクローン・セットアップ

```bash
# クローン
git clone <repo-url>
cd GootPhotoSelector

# 「送る」メニューへの登録（Windows・初回のみ）
bin\setup_sendto.bat をダブルクリック
```

OpenCV は任意です。未導入の場合、鮮明度ヒントと顔クロップ確認をスキップします。

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

### コマンドから実行

```bash
python3 src/select_photos.py /path/to/photos
python3 src/select_photos.py /path/to/photos --dry-run
python3 src/select_photos.py DSC_0001.NEF DSC_0002.NEF --model opus
```

`--dry-run` はコンタクトシートを生成して表示し、Claude 呼び出しと XMP 書き込みを行いません。`--keep-previews` を付けると一時プレビューとシートを残します。

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
  └─ Pillow + struct で最大の内蔵 JPEG を抽出して縮小
       └─ 撮影時刻で連写をクラスタリング
            └─ 番号付きコンタクトシートを Claude が構造化判定
                 └─ src/set_label.py で XMP サイドカーに xmpDM:good を書き込み
                      └─ Lightroom で採用/不採用ラベルとして表示
```

## ファイル構成

```
GootPhotoSelector/
├── bin/
│   ├── good_photo_selector.bat   # 「送る」ショートカットのターゲット
│   ├── good_photo_selector.sh    # Python ドライバー起動スクリプト
│   └── setup_sendto.bat          # 「送る」メニュー登録ツール
├── src/
│   ├── select_photos.py    # NEF 選別ドライバー
│   ├── nef_preview.py      # 内蔵 JPEG と撮影時刻の抽出
│   ├── quality.py          # 品質ヒント・顔クロップの T1 スタブ
│   ├── set_label.py        # XMP サイドカー書き込みライブラリ
│   ├── prompts/            # Claude 判定プロンプト
│   └── schemas/            # Claude 構造化出力スキーマ
├── settings/
│   └── config.ini.example  # モデル・連写・シート設定
├── tests/                  # pytest による回帰テスト
├── contracts/              # 実測 CLI / NEF 契約
├── docs/
│   └── xmp_sample/         # 採用・不採用・評価なしの XMP サンプル
├── CLAUDE.md               # Claude Code 向けガイド
└── AGENTS.md               # AI エージェント向けガイド
```
