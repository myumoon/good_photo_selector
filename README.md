# GootPhotoSelector

Claude Code を使って Nikon NEF 写真を自動選別し、Lightroom 互換の XMP ラベルを付けるツール。

## 概要

同一シチュエーションで撮った複数枚の写真を Claude が評価し、表情・構図・ピントを基準に採用/不採用を判定。  
判定結果は XMP サイドカーファイル（`xmpDM:good`）として保存され、Lightroom でそのまま確認できる。

## 動作環境

- Windows 10/11（WSL 不要）
- Python 3.9 以上（`python` コマンドを PATH に登録）
- Pillow
- Claude Code ネイティブ Windows 版（`claude` コマンドを PATH に登録）
- Adobe Lightroom（結果確認用）
- OpenCV は任意です。未導入の場合、鮮明度ヒントと顔確認をスキップします。

## セットアップ

### 1. リポジトリをクローンして依存関係をセットアップ

```powershell
git clone <repo-url>
cd GootPhotoSelector
bin\setup.bat
```

先に Python 3.9 以上と Claude Code のネイティブ Windows 版をインストールし、`python` と `claude` を PATH から実行できるようにしてください。`bin\setup.bat` は両方の有無を確認し、Pillow、NumPy、OpenCV をインストールします。OpenCV は任意で、未導入の場合は鮮明度ヒントと顔確認をスキップします。

### 2. 「送る」メニューへの登録（初回のみ）

```powershell
bin\setup_sendto.bat
```

`bin/good_photo_selector.sh` は Linux/WSL から手動実行する場合の補助スクリプトです。その環境にも Python と Claude Code が必要です。WSL に Claude Code がない場合は実行できません。

## 使い方

### 右クリックから起動（推奨）

**フォルダ指定モード** — フォルダ内の全 NEF を処理する:

1. エクスプローラーで NEF ファイルが入ったフォルダを右クリック
2. **送る → GootPhotoSelector**
3. Windows のコンソールで Claude が自動選別を実行
4. 完了後に `Selection complete: X accepted / Y rejected` と表示
5. Enter で閉じる

**ファイル指定モード** — 選んだファイルだけを処理する:

1. エクスプローラーで処理したい NEF ファイルを複数選択
2. 右クリック → **送る → GootPhotoSelector**
3. 以降は同じ

### コマンドから実行

```powershell
python src\select_photos.py "C:\path\to\photos"
python src\select_photos.py "C:\path\to\photos" --dry-run
python src\select_photos.py "C:\path\DSC_0001.NEF" "C:\path\DSC_0002.NEF" --model opus
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
「送る」メニュー
  └─ good_photo_selector.bat
       └─ python src\select_photos.py
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
│   ├── good_photo_selector.sh    # Linux/WSL から手動実行する補助スクリプト
│   ├── setup.bat                 # Windows 用依存関係セットアップ
│   ├── setup.sh                  # Linux/WSL 用セットアップ
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
