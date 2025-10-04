# デプロイガイド

このガイドでは、PDF OCR APIをデプロイする方法を説明します。

## 前提条件

- Docker がインストールされていること
- Docker Compose がインストールされていること（オプション）
- または、Fly.io、AWS、GCP、Azureなどのクラウドプラットフォームのアカウント

## オプション1: Dockerでローカルにデプロイ

### ステップ1: Dockerイメージのビルド

```bash
cd pdf_ocr_backend
docker build -t pdf-ocr-api .
```

### ステップ2: コンテナの実行

```bash
docker run -d -p 8000:8000 --name pdf-ocr-api pdf-ocr-api
```

APIは http://localhost:8000 でアクセス可能になります。

### ステップ3: 動作確認

```bash
curl http://localhost:8000/healthz
```

## オプション2: Docker Composeでデプロイ

### ステップ1: サービスの起動

```bash
cd pdf_ocr_backend
docker-compose up -d
```

### ステップ2: ログの確認

```bash
docker-compose logs -f
```

### ステップ3: サービスの停止

```bash
docker-compose down
```

## オプション3: Fly.ioにデプロイ

Fly.ioは無料枠があり、カスタムDockerfileをサポートしています。

### ステップ1: Fly CLIのインストール

```bash
curl -L https://fly.io/install.sh | sh
```

### ステップ2: Fly.ioにログイン

```bash
fly auth login
```

### ステップ3: アプリの作成

```bash
cd pdf_ocr_backend
fly launch
```

プロンプトに従って設定します：
- アプリ名を選択
- リージョンを選択（日本の場合は `nrt`）
- PostgreSQLは不要なので「No」を選択

### ステップ4: デプロイ

```bash
fly deploy
```

デプロイが完了すると、公開URLが表示されます。

### ステップ5: ログの確認

```bash
fly logs
```

## オプション4: Herokuにデプロイ

### ステップ1: Heroku CLIのインストール

```bash
# macOS
brew tap heroku/brew && brew install heroku

# Ubuntu
curl https://cli-assets.heroku.com/install.sh | sh
```

### ステップ2: ログインとアプリ作成

```bash
heroku login
cd pdf_ocr_backend
heroku create your-app-name
```

### ステップ3: Heroku.ymlの作成

Heroku用の設定ファイルを作成します：

```yaml
build:
  docker:
    web: Dockerfile
run:
  web: fastapi run app/main.py --host 0.0.0.0 --port $PORT
```

### ステップ4: デプロイ

```bash
git init
git add .
git commit -m "Initial commit"
heroku git:remote -a your-app-name
git push heroku main
```

## オプション5: AWS、GCP、Azureにデプロイ

### AWS (ECS/Fargate)

1. DockerイメージをECRにプッシュ
2. ECSタスク定義を作成
3. ECSサービスを作成

### Google Cloud Run

```bash
gcloud run deploy pdf-ocr-api \
  --source . \
  --platform managed \
  --region asia-northeast1 \
  --allow-unauthenticated
```

### Azure Container Instances

```bash
az container create \
  --resource-group myResourceGroup \
  --name pdf-ocr-api \
  --image pdf-ocr-api \
  --dns-name-label pdf-ocr-api \
  --ports 8000
```

## 環境変数（オプション）

必要に応じて環境変数を設定できます：

```bash
# Docker
docker run -d -p 8000:8000 \
  -e ENVIRONMENT=production \
  --name pdf-ocr-api pdf-ocr-api

# Docker Compose
# docker-compose.ymlに追加:
environment:
  - ENVIRONMENT=production
  - MAX_FILE_SIZE=10485760  # 10MB
```

## トラブルシューティング

### OCRツールが見つからないエラー

Dockerfileにすべての必要な依存関係が含まれていることを確認してください：
- tesseract-ocr
- tesseract-ocr-jpn
- tesseract-ocr-eng
- poppler-utils
- qpdf

### メモリ不足エラー

大きなPDFを処理する場合、メモリ制限を増やす必要があります：

```bash
docker run -d -p 8000:8000 --memory=2g --name pdf-ocr-api pdf-ocr-api
```

### ポートが使用中

ポート8000が既に使用されている場合は、別のポートにマッピングします：

```bash
docker run -d -p 8080:8000 --name pdf-ocr-api pdf-ocr-api
```

## セキュリティ考慮事項

本番環境では以下を検討してください：

1. **認証の追加**: APIキーまたはOAuthを実装
2. **レート制限**: リクエスト制限を設定
3. **ファイルサイズ制限**: 大きすぎるファイルを拒否
4. **HTTPS**: SSL/TLS証明書を使用
5. **ログ記録**: アクセスログとエラーログを記録

## パフォーマンス最適化

1. **ワーカー数の調整**: Uvicornのworker数を増やす
2. **キャッシング**: よく使用される結果をキャッシュ
3. **非同期処理**: 大きなファイルのバックグラウンド処理
4. **CDN**: 静的ファイル用のCDNを使用

## モニタリング

推奨されるモニタリングツール：
- Prometheus + Grafana
- Datadog
- New Relic
- CloudWatch (AWS)
- Stackdriver (GCP)

## サポート

問題が発生した場合は、以下を確認してください：
1. Dockerログ: `docker logs pdf-ocr-api`
2. システム依存関係が正しくインストールされているか
3. ポートが開いているか
4. メモリとCPUリソースが十分にあるか
