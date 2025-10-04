# PDF OCR API

PDFファイルをOCR処理して検索可能なPDFに変換するWeb APIです。

Qiitaの記事「[PythonでPDFに文字埋め込みたい。（PyOCR + pdf2image + Tesseract)](https://qiita.com/Ryo-F/items/9cc168bc5e531e223f27)」に基づいて実装されています。

## 機能

- PDFファイルをアップロードしてOCR処理
- Tesseract OCRで文字認識
- 検索可能なPDFを生成して返却
- 日本語、英語、または両方の言語をサポート

## 技術スタック

- **FastAPI**: Web APIフレームワーク
- **PyOCR**: Tesseract OCRのPythonラッパー
- **pdf2image**: PDFを画像に変換
- **Tesseract OCR**: 文字認識エンジン
- **qpdf**: PDF操作ツール（テキストレイヤーをオーバーレイ）

## API エンドポイント

### `GET /`
APIの情報と利用可能なエンドポイントを返します。

**レスポンス例:**
```json
{
  "message": "PDF OCR API",
  "endpoints": {
    "/ocr-pdf": "POST - Upload a PDF file to convert it to searchable PDF",
    "/healthz": "GET - Health check"
  }
}
```

### `POST /ocr-pdf`
PDFファイルをアップロードしてOCR処理を行い、検索可能なPDFを返します。

**パラメータ:**
- `file` (required): アップロードするPDFファイル
- `language` (optional): OCR言語 (`jpn`, `eng`, `jpn+eng`のいずれか。デフォルト: `jpn`)

**使用例:**
```bash
curl -X POST "http://localhost:8000/ocr-pdf" \
  -F "file=@input.pdf" \
  -F "language=jpn" \
  -o searchable_output.pdf
```

**レスポンス:**
- 成功時: 検索可能なPDFファイル (Content-Type: application/pdf)
- エラー時: JSON形式のエラーメッセージ

### `GET /healthz`
ヘルスチェックエンドポイント。

**レスポンス例:**
```json
{"status": "ok"}
```

## ローカルでの実行

### 前提条件

システム依存関係をインストール:
```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-jpn tesseract-ocr-eng poppler-utils qpdf
```

### インストール

```bash
# 依存関係のインストール
poetry install

# 開発サーバーの起動
poetry run fastapi dev app/main.py
```

サーバーは http://localhost:8000 で起動します。

APIドキュメント: http://localhost:8000/docs

## Dockerでのデプロイ

### Dockerイメージのビルド

```bash
docker build -t pdf-ocr-api .
```

### Dockerコンテナの実行

```bash
docker run -p 8000:8000 pdf-ocr-api
```

### Docker Composeでの実行

```bash
docker-compose up
```

## 処理フロー

1. PDFファイルを受信
2. PDFを画像に変換（pdf2image + poppler）
3. 各ページの画像をTIFFファイルに結合
4. Tesseract OCRでテキスト抽出とテキストのみのPDF生成
5. qpdfで元のPDFにテキストレイヤーをオーバーレイ
6. 検索可能なPDFを返却

## エラーハンドリング

- `400 Bad Request`: PDFファイル以外のファイル、または無効な言語パラメータ
- `500 Internal Server Error`: OCRツールが見つからない、またはOCR処理に失敗

## ライセンス

このプロジェクトは教育目的で作成されました。

## 参考文献

- [PythonでPDFに文字埋め込みたい。（PyOCR + pdf2image + Tesseract)](https://qiita.com/Ryo-F/items/9cc168bc5e531e223f27)
