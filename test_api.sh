#!/bin/bash

echo "==================================="
echo "PDF OCR API テストスクリプト"
echo "==================================="
echo ""

API_URL=${1:-"http://localhost:8000"}

echo "テスト対象: $API_URL"
echo ""

echo "1. ヘルスチェック..."
curl -s "$API_URL/healthz" | jq .
echo ""

echo "2. ルートエンドポイント..."
curl -s "$API_URL/" | jq .
echo ""

echo "3. サンプルPDFファイルをダウンロード..."
if [ ! -f "集成第一マンション.pdf" ]; then
    wget -q -O 集成第一マンション.pdf "http://www.0359370391.com/list/2020102900020/file_contents/3.pdf"
    echo "✓ 集成第一マンション.pdf をダウンロードしました"
else
    echo "✓ 集成第一マンション.pdf は既に存在します"
fi
echo ""

echo "4. PDF OCR処理をテスト（英語）..."
curl -X POST "$API_URL/ocr-pdf" \
  -F "file=@test_sample.pdf" \
  -F "language=eng" \
  -o output_eng.pdf \
  -w "\nHTTP Status: %{http_code}\n"

if [ -f "output_eng.pdf" ]; then
    SIZE=$(ls -lh output_eng.pdf | awk '{print $5}')
    echo "✓ 検索可能なPDFを生成しました: output_eng.pdf ($SIZE)"
else
    echo "✗ PDF生成に失敗しました"
fi
echo ""

echo "==================================="
echo "テスト完了"
echo "==================================="
