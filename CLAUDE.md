# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

GootPhotoSelector — **明らかに写りが悪い写真を除外（不採用）する**ための写真セレクトツール。
良い写真を選び抜くのではなく、ブレ・ピンボケなど明らかにダメな写真をふるい落とすのが主目的。
ClaudeがNEFファイルを評価し、XMPサイドカーにラベル（採用 / 不採用 / フラグなし）を書き込む。

## 使い方

ユーザーから「`<DIR>` の写真を選別して」と依頼されたときの手順:

> **ファイル指定モード**: 特定のNEFファイルをリストで渡された場合は手順1をスキップし、そのファイルだけを対象に手順2から実行する。

### 1. NEFファイルの一覧取得

```bash
ls <DIR>/*.NEF
```

### 2. 全NEFからJPEGを一括並列抽出

評価を始める前に、全ファイルのJPEGを一度に並列抽出する。

まず `settings/*.ini` から解像度を読み込む（なければデフォルト 640px）:

```bash
RESOLUTION=640
for ini in settings/*.ini; do
  [ -f "$ini" ] || break
  val=$(grep -E '^\s*resolution\s*=' "$ini" | head -1 | sed 's/.*=\s*//; s/[^0-9].*//')
  [ -n "$val" ] && RESOLUTION=$val
  break
done
echo "Preview resolution: ${RESOLUTION}px"
```

解像度に応じて並列抽出する:

```
Extracting all previews in parallel...
```

```bash
if [ "$RESOLUTION" -gt 640 ] && command -v convert &>/dev/null; then
  # JpgFromRaw を指定解像度にリサイズ（高品質・ImageMagick 必須）
  for nef in <DIR>/*.NEF; do
    base=$(basename "$nef" .NEF)
    exiftool -b -JpgFromRaw "$nef" | convert - -resize "${RESOLUTION}x${RESOLUTION}>" /tmp/${base}.jpg &
  done
else
  # PreviewImage (640px) をそのまま使用（高速・ImageMagick 不要）
  for nef in <DIR>/*.NEF; do
    base=$(basename "$nef" .NEF)
    exiftool -b -PreviewImage "$nef" > /tmp/${base}.jpg &
  done
fi
wait
echo "Extraction complete."
```

### 3. 連写(シーン)単位で評価・ラベル書き込み

写真は**連写(同一シーン)ごとにまとめて評価**する。4枚固定バッチだと連写が分断され、
「シーン内ベスト1枚」を選べないため、まず撮影時刻でシーンをクラスタリングする:

```bash
python3 src/cluster_bursts.py <DIR>
```

出力の**1連写(1行)を1バッチ**として、各連写で以下のStep 1〜2を繰り返す。

#### Step 1: 連写内の全画像を一度に読み込んで評価

`Read` ツールで連写内の全JPEGを読み込み、**シーン全体を見比べて採否を決定**する。
連写が十数枚以上と多い場合は分割して読み込んでよいが、**採用の判断は連写全体を通して行う**
（先に見た数枚だけで採用を確定しない）。採否の考え方は後述「選別基準」に従う。

#### Step 2: 連写内の全ファイルにラベルを書き込む

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
[N/M] DSC_1236.NEF → unrated
```

### 4. 後片付け

```bash
rm /tmp/DSC_*.jpg
```

---

## 選別基準

> **このツールの目的: 「良い写真を選び抜く」のではなく「明らかに写りが悪い写真を除外する」こと。**
> デフォルトは **フラグなし（評価なし / None）**。明らかにダメな写真だけを **不採用** にし、**採用はごく例外的にしか付けない**（プロ基準で明らかに良い、または同一シチュエーションで唯一残った1枚のときだけ）。

### 判定フロー

写真は **同一シチュエーション**（連写・同じ被写体/構図のまとまり・同じ風景/モノ）ごとに判断する。各写真を次の順で振り分ける:

1. **明らかに写りが悪い → 不採用（False）**
   - ブレている / 被写体にピントが合っていない
   - 半目・表情の崩れなど明らかに失敗している
   - 連写・複数枚がある場合、他と比べて明らかに写りが劣るもの
2. **上記以外 → 基本はフラグなし（None）**
   - 連写の場合: 写りが良いと思ったものをフラグなしにし、**それ以外は不採用**にする
3. **採用（True）は次のどちらかのときだけ付ける**
   - **明らかに写りが良い**（プロ基準でも通用する）写真
   - **同一シチュエーションでフラグなし（＝非不採用）が結果的に1枚だけになった**場合、その1枚を採用にする
     （＝他の写真がすべて不採用になり、実質その1枚だけが残ったケース）

### 「明らかに写りが悪い」＝不採用の例

- ブレている写真
- 被写体にピントが合っていない写真 / 人物メインで顔がボケている写真
- 半目（まばたき）の写真 ※眩しさで目を細めた良い表情や、意図的に閉じた面白い表情は「悪い」に含めない
- 連写・複数枚の中で、他より明らかに写りが劣るもの

### 写りの良し悪しを見る観点

以下は「採用」に直結する条件ではなく、**不採用にするか／フラグなしに残すか**、また突出して良ければ採用するかを判断するための材料:

- 笑っている / 目がキラキラしている / 生き生きした表情
- カメラ目線（複数人なら全員がカメラ目線だと尚良い）
- 眩しそうに目を細めた表情・意図的に目を閉じた面白い表情など、印象的な表情
- 構図が良い / 奥行き感・立体感がある（前景と背景の遠近が効いている）
- 意図的に後ろ・横を向いた構図で、視線の先に空間（余白・抜け感）がある
- 特徴的なポーズ・フォームで被写体にピントが合っている
- 前ボケ（ボケた前景）が印象的・美しい

### 風景画・モノの写真

- 人物写真と同じ基準。
- **1枚しかない場合 → 採用**
- **複数枚ある場合 → 写りが悪いものを不採用にし、残りは基本フラグなし**（結果的に1枚しか残らなければ、その1枚は採用）

### 評価対象外

- ライティングはLightroomで調整するため評価の対象外
- 被写体の傾き(補正可能)

### 補足

- **`None`（XMP属性なし）と「XMPサイドカーそのものが無い」状態は同義**。既存フラグを読む際は **XMPなし = 評価なし = フラグなし** とみなす。ツールが書き込む際は `set_label.py None`（属性なしXMP）で表現する。
- 連写(シーン)全体を見てから採否を確定する。連写が複数バッチにまたがる場合は、グループ全体を見比べてから判断する（`src/cluster_bursts.py` でシーン単位にまとめる）。

## 仕分けルール

Lightroomの `xmpDM:good` フィールドで制御する:

| 値 | 意味 |
|---|---|
| `"True"` | 採用（プロ基準で明らかに良い or 同一シーンで唯一残った1枚） |
| `"False"` | 不採用（明らかに写りが悪い） |
| (属性なし) | 評価なし・フラグなし（**デフォルト**） |
| (XMPサイドカーなし) | 評価なし（属性なしと同義） |

- 評価なし（フラグなし）は「属性なしXMP」と「XMPサイドカーなし」のどちらでも同義として扱う
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
