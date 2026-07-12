# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

GootPhotoSelector — 同一シチュエーションの写真を表情・構図の良い写真に厳選するツール。
ClaudeがNEFファイルを評価してXMPサイドカーに採用/不採用ラベルを書き込む。

## 使い方

ユーザーから「`<DIR>` の写真を選別して」と依頼されたときの手順:

> **ファイル指定モード**: 特定のNEFファイルをリストで渡された場合は手順1をスキップし、そのファイルだけを対象に手順2から実行する。

### 1. NEFファイルの一覧取得

```bash
ls <DIR>/*.NEF
```

### 2. 全NEFからJPEGを一括並列抽出

評価を始める前に、全ファイルのJPEGを一度に並列抽出する。

```
Extracting all previews in parallel...
```

```bash
if command -v convert &>/dev/null; then
  for nef in <DIR>/*.NEF; do
    base=$(basename "$nef" .NEF)
    exiftool -b -JpgFromRaw "$nef" | convert - -resize "1280x1280>" /tmp/${base}.jpg &
  done
else
  for nef in <DIR>/*.NEF; do
    base=$(basename "$nef" .NEF)
    exiftool -b -PreviewImage "$nef" > /tmp/${base}.jpg &
  done
fi
wait
echo "Extraction complete."
```

### 3. バッチ処理で評価・ラベル書き込み

**4枚ずつのバッチ**に分けて処理する。各バッチで以下のStep 1〜2を繰り返す。

#### Step 1: バッチ内の全画像を一度に読み込んで評価

`Read` ツールでバッチ内の全JPEGを読み込み、**まとめて採否を決定**する。

#### Step 2: バッチ内の全ファイルにラベルを書き込む

```bash
# 採用
python3 src/set_label.py "<DIR>/DSC_1234.NEF" True

# 不採用
python3 src/set_label.py "<DIR>/DSC_1234.NEF" False

# 評価なし（ラベル削除）
python3 src/set_label.py "<DIR>/DSC_1234.NEF" None
```

XMPサイドカー（`<DIR>/DSC_1234.xmp`）が自動的に作成・更新される。

ラベル書き込み後に結果を出力する（テキスト出力として必ず行うこと）:

```
[N/M] DSC_1234.NEF → accepted
[N/M] DSC_1235.NEF → rejected
```

### 4. 後片付け

```bash
rm /tmp/DSC_*.jpg
```

---

## 選別基準

### 採用写真

- 笑っている写真
- カメラ目線の写真
- 構図がいい写真
- 特徴的なポーズ・フォームで被写体にピントが合っている写真
- 前ボケ（ボケた前景）が印象的・美しい写真

### 不採用写真

- ブレている写真
- 半目の写真
- 人物メインで顔がボケている写真

### 評価対象外

- ライティングはLightroomで調整するため評価の対象外
- 被写体の傾き(補正可能)

### 補足

- 風景画などで同じような写真が複数ある場合はClaudeがいい写真を判断して1枚選ぶ
- 同一シーンの複数枚から選ぶ際は、**奥行き感・立体感がある写真を優先**する（前景と背景の遠近が効いている写真を選ぶ）

## 仕分けルール

Lightroomの `xmpDM:good` フィールドで制御する:

| 値 | 意味 |
|---|---|
| `"True"` | 採用 |
| `"False"` | 不採用 |
| (属性なし) | 評価なし |

- XMPサイドカーが存在しない場合は新規作成する
- 既存XMPはカメラ設定等を保持したまま `xmpDM:good` のみ更新する
- exiftoolは属性形式を要素形式に変換してしまうため書き込みには使用しない

## ディレクトリ構成

| フォルダ | 役割 |
|---|---|
| `src/` | ソースコード |
| `docs/` | ドキュメント |
| `.env/` | 検証用入力写真置き場（gitignore対象） |

## ツール

- **exiftool**: WSL 内で `sudo apt install libimage-exiftool-perl` でインストール。Windows の場合は [exiftool.org](https://exiftool.org/) からダウンロードして PATH に配置
  - 用途: NEFからのJPEGプレビュー抽出、XMPの読み取り確認など
- **ImageMagick**: WSL 内で `sudo apt install imagemagick` でインストール
  - 用途: 抽出JPEGのリサイズ（トークン削減）

## サンプルXMP

`docs/xmp_sample/` に採用・不採用・評価なしの実際のXMPファイルが格納されている。フォーマット確認に使用すること。

## 「送る」メニューからの起動

### 初回セットアップ（一度だけ）

`bin\setup_sendto.bat` をダブルクリックすると、右クリック → 送る に「写真選別」が登録される。

### 使い方

1. エクスプローラーで NEF ファイルが入ったフォルダを右クリック
2. 送る → GootPhotoSelector
3. WSL ターミナルが開き、Claude が自動で選別を実行
4. 完了後に「Selection complete: X accepted / Y rejected」と表示される
5. Enter で閉じる

### 仕組み

```
good_photo_selector.bat  ← 「送る」ショートカットのターゲット
  │ Windowsパス → WSLパスに変換
  └→ WSL で good_photo_selector.sh <folder> を起動
       └→ claude --dangerously-skip-permissions -p "..."
```

### 補足

- 複数フォルダを同時に送ると、それぞれ別の WSL ウィンドウで並行処理される
