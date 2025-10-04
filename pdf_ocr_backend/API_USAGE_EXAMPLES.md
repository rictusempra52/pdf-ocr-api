# API使用例

## 基本的な使用方法

### 1. ヘルスチェック

```bash
curl http://localhost:8000/healthz
```

**レスポンス:**
```json
{"status": "ok"}
```

### 2. API情報の取得

```bash
curl http://localhost:8000/
```

**レスポンス:**
```json
{
  "message": "PDF OCR API",
  "endpoints": {
    "/ocr-pdf": "POST - Upload a PDF file to convert it to searchable PDF",
    "/healthz": "GET - Health check"
  }
}
```

### 3. PDFをOCR処理（日本語）

```bash
curl -X POST "http://localhost:8000/ocr-pdf" \
  -F "file=@document.pdf" \
  -F "language=jpn" \
  -o searchable_document.pdf
```

### 4. PDFをOCR処理（英語）

```bash
curl -X POST "http://localhost:8000/ocr-pdf" \
  -F "file=@document.pdf" \
  -F "language=eng" \
  -o searchable_document.pdf
```

### 5. PDFをOCR処理（日本語+英語）

```bash
curl -X POST "http://localhost:8000/ocr-pdf" \
  -F "file=@document.pdf" \
  -F "language=jpn+eng" \
  -o searchable_document.pdf
```

## Pythonでの使用例

```python
import requests

# APIエンドポイント
url = "http://localhost:8000/ocr-pdf"

# PDFファイルを開く
with open("input.pdf", "rb") as f:
    files = {"file": ("input.pdf", f, "application/pdf")}
    data = {"language": "jpn"}
    
    # リクエストを送信
    response = requests.post(url, files=files, data=data)
    
    # 検索可能なPDFを保存
    if response.status_code == 200:
        with open("searchable_output.pdf", "wb") as out:
            out.write(response.content)
        print("OCR処理完了")
    else:
        print(f"エラー: {response.json()}")
```

## JavaScriptでの使用例

```javascript
// ブラウザでの使用（HTML formから）
const formData = new FormData();
formData.append('file', pdfFile);
formData.append('language', 'jpn');

fetch('http://localhost:8000/ocr-pdf', {
  method: 'POST',
  body: formData
})
  .then(response => response.blob())
  .then(blob => {
    // ダウンロード用のリンクを作成
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'searchable_output.pdf';
    a.click();
  })
  .catch(error => console.error('Error:', error));
```

## Node.jsでの使用例

```javascript
const fs = require('fs');
const FormData = require('form-data');
const axios = require('axios');

async function ocrPdf(inputPath, outputPath, language = 'jpn') {
  const form = new FormData();
  form.append('file', fs.createReadStream(inputPath));
  form.append('language', language);

  try {
    const response = await axios.post('http://localhost:8000/ocr-pdf', form, {
      headers: form.getHeaders(),
      responseType: 'arraybuffer'
    });

    fs.writeFileSync(outputPath, response.data);
    console.log('OCR処理完了');
  } catch (error) {
    console.error('エラー:', error.response?.data || error.message);
  }
}

// 使用例
ocrPdf('input.pdf', 'searchable_output.pdf', 'jpn');
```

## エラーハンドリング例

```python
import requests

url = "http://localhost:8000/ocr-pdf"

try:
    with open("input.pdf", "rb") as f:
        files = {"file": ("input.pdf", f, "application/pdf")}
        data = {"language": "jpn"}
        
        response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            with open("searchable_output.pdf", "wb") as out:
                out.write(response.content)
            print("OCR処理成功")
        elif response.status_code == 400:
            error_detail = response.json()["detail"]
            print(f"リクエストエラー: {error_detail}")
        elif response.status_code == 500:
            error_detail = response.json()["detail"]
            print(f"サーバーエラー: {error_detail}")
        else:
            print(f"予期しないエラー: {response.status_code}")
            
except FileNotFoundError:
    print("入力ファイルが見つかりません")
except requests.exceptions.ConnectionError:
    print("APIサーバーに接続できません")
except Exception as e:
    print(f"エラー: {str(e)}")
```

## バッチ処理の例

複数のPDFファイルを一括処理：

```python
import os
import requests
from pathlib import Path

def batch_ocr(input_dir, output_dir, language="jpn"):
    url = "http://localhost:8000/ocr-pdf"
    
    # 出力ディレクトリを作成
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 入力ディレクトリ内のすべてのPDFファイルを処理
    for filename in os.listdir(input_dir):
        if filename.endswith('.pdf'):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, f"searchable_{filename}")
            
            print(f"処理中: {filename}")
            
            try:
                with open(input_path, "rb") as f:
                    files = {"file": (filename, f, "application/pdf")}
                    data = {"language": language}
                    
                    response = requests.post(url, files=files, data=data)
                    
                    if response.status_code == 200:
                        with open(output_path, "wb") as out:
                            out.write(response.content)
                        print(f"✓ 完了: {filename}")
                    else:
                        print(f"✗ 失敗: {filename} - {response.json()}")
                        
            except Exception as e:
                print(f"✗ エラー: {filename} - {str(e)}")

# 使用例
batch_ocr("./input_pdfs", "./output_pdfs", language="jpn")
```

## APIドキュメント（Swagger UI）

FastAPIは自動的にインタラクティブなAPIドキュメントを生成します：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

ブラウザでこれらのURLにアクセスすると、APIを試すことができます。
