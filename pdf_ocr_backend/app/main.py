import logging
import uuid
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import pyocr
import pyocr.builders
from pdf2image import convert_from_path
import subprocess
import os
import tempfile
import shutil
import json
import csv
from pathlib import Path
from PIL import Image

# --- 1. 準備：ログと進捗管理の設定 ---

# ログの設定（プログラムの動きを日本語で出力するようにします）
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 進捗管理ノート（辞書型）
# 構造: jobs[job_id] = {"status": "進行中", "progress": 50, "result_file": "path", "filename": "..."}
jobs = {}

# 完成したファイルを一時保存する場所（コンテナ内の永続ディレクトリを想定）
RESULTS_DIR = Path("/app/storage/ocr_results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PDF OCR API", description="Convert scanned PDFs to searchable PDFs using OCR")

# --- 2. CORS設定（セキュリティ） ---

# 環境変数から許可するURLを取得します（カンマ区切りで複数指定可能）
# 例: ALLOWED_ORIGINS=http://localhost:3000,https://my-app.vercel.app
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")

# "*"（すべて許可）でない場合は、カンマで分割してリストにします
if allowed_origins_raw == "*":
    allow_origins = ["*"]
else:
    allow_origins = [origin.strip() for origin in allowed_origins_raw.split(",")]

logger.info(f"CORS許可設定: {allow_origins}")

# CORS設定（他のWebアプリから接続できるようにする設定）
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,  # 許可されたURLのリストを適用
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 3. ユーティリティ関数 ---

def parse_tsv(tsv_path: Path, target_level: int = 4):
    """
    TesseractのTSVファイルを解析して指定されたレベルの項目リストを返します。
    上位レベル(1-4)が指定された場合、その配下にある Word (level 5) のテキストを連結して返します。
    """
    if not tsv_path.exists():
        return []

    all_rows = []
    with open(tsv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
        all_rows = list(reader)

    items = []
    for i, row in enumerate(all_rows):
        # 指定されたレベルの行を見つけたら
        if row.get('level') == str(target_level):
            try:
                item = {
                    "text": "",
                    "confidence": int(float(row.get('conf', 0))),
                    "bbox": {
                        "left": int(row.get('left', 0)),
                        "top": int(row.get('top', 0)),
                        "width": int(row.get('width', 0)),
                        "height": int(row.get('height', 0))
                    }
                }

                # もし target_level が Word (5) ならそのまま text を使用
                if target_level == 5:
                    item["text"] = row.get('text', '').strip()
                else:
                    # target_level が 1-4 の場合、次の target_level の行が出てくるまでの間にある
                    # level 5 (Word) のテキストをすべて連結する
                    words_in_item = []
                    confidences = []
                    
                    for j in range(i + 1, len(all_rows)):
                        next_row = all_rows[j]
                        # 同じレベルか、より上位のレベルの行が出てきたら終了
                        if int(next_row.get('level', 0)) <= target_level:
                            break
                        
                        # Word レベルのテキストを収集
                        if next_row.get('level') == '5':
                            w_text = next_row.get('text', '').strip()
                            if w_text:
                                words_in_item.append(w_text)
                                conf_val = int(float(next_row.get('conf', 0)))
                                if conf_val >= 0: # -1 は無視
                                    confidences.append(conf_val)
                    
                    item["text"] = "".join(words_in_item) # 日本語なのでスペースなしで結合
                    if confidences:
                        item["confidence"] = int(sum(confidences) / len(confidences))
                
                # テキストがある場合、または Page/Block 等で領域として意味がある場合に追加
                if item["text"] or target_level < 4:
                    items.append(item)
                    
            except (ValueError, TypeError):
                continue
    return items

# --- 4. バックグラウンドで行う重い処理（OCR本体） ---

def run_ocr_task(job_id: str, temp_dir: str, pdf_path: Path, language: str, original_filename: str, ocr_level: int = 4):
    """
    裏側で実行される重い処理（注文ベルが鳴った後に店員がやる作業）
    """
    try:
        # 進捗を0%にセット
        jobs[job_id] = {
            "status": "processing",
            "progress": 0,
            "filename": original_filename
        }
        
        # 1ページずつ画像に変換して保存
        output_images_dir = Path(temp_dir) / "images"
        output_images_dir.mkdir(exist_ok=True)
        
        logger.info(f"[{job_id}] PDFを画像に変換中...")
        image_paths = convert_from_path(
            str(pdf_path), 
            300, 
            output_folder=str(output_images_dir),
            fmt="tiff",
            paths_only=True
        )
        
        total_pages = len(image_paths)
        textonly_pdfs = []
        structured_pages = []
        
        # 1ページずつOCRを実行
        for i, img_path in enumerate(image_paths):
            page_num = i + 1
            
            # 画像サイズを取得
            with Image.open(img_path) as img:
                width, height = img.size

            # ノートの進捗率を更新
            progress_percent = int((i / total_pages) * 100)
            jobs[job_id]["progress"] = progress_percent
            logger.info(f"[{job_id}] 進行状況: {page_num}/{total_pages} ページ目を処理中 ({progress_percent}%)")
            
            page_base = Path(temp_dir) / f"page_{page_num}"
            page_pdf = Path(temp_dir) / f"page_{page_num}.pdf"
            page_tsv = Path(temp_dir) / f"page_{page_num}.tsv"
            
            # tsv と pdf の両方を出力
            cmd = [
                "tesseract",
                "-c", "textonly_pdf=1",
                str(img_path),
                str(page_base),
                "-l", language,
                "pdf", "tsv"
            ]
            
            subprocess.run(cmd, check=True)
            textonly_pdfs.append(str(page_pdf))
            
            # TSVを解析して構造化データに追加（指定されたレベルで取得）
            page_items = parse_tsv(page_tsv, target_level=ocr_level)
            structured_pages.append({
                "page_number": page_num,
                "width": width,
                "height": height,
                "level": ocr_level,
                "items": page_items
            })
            
        logger.info(f"[{job_id}] 全ページのOCRが完了。結合中...")
        
        # 完了したPDFを作成
        combined_text_pdf = Path(temp_dir) / "combined.pdf"
        subprocess.run(["qpdf", "--empty", "--pages"] + textonly_pdfs + ["--", str(combined_text_pdf)], check=True)
        
        final_pdf_path = RESULTS_DIR / f"{job_id}.pdf"
        subprocess.run([
            "qpdf", "--overlay", str(combined_text_pdf), "--", 
            str(pdf_path), str(final_pdf_path)
        ], check=True)

        # 構造化JSONを保存
        final_json_data = {
            "job_id": job_id,
            "filename": original_filename,
            "total_pages": total_pages,
            "pages": structured_pages
        }
        final_json_path = RESULTS_DIR / f"{job_id}.json"
        with open(final_json_path, "w", encoding="utf-8") as f:
            json.dump(final_json_data, f, ensure_ascii=False, indent=2)
        
        # ノートを「完了」に書き換える（巨大なデータは持たずファイルパスのみ保持）
        jobs[job_id].update({
            "status": "completed",
            "progress": 100,
            "result_file": str(final_pdf_path),
            "result_json": str(final_json_path)
        })
        logger.info(f"[{job_id}] 全ての処理が完了しました。")
        
    except Exception as e:
        logger.exception(f"[{job_id}] エラーが発生しました")
        jobs[job_id] = {"status": "failed", "error": str(e)}
    finally:
        # 元のPDFが入った一時ディレクトリを削除（結果のPDFはRESULTS_DIRに移動済み）
        shutil.rmtree(temp_dir, ignore_errors=True)

# --- 3. API窓口（エンドポイント） ---

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "PDF OCR API (Async Support)"}

@app.post("/ocr-pdf", summary="PDF OCR処理の予約", response_description="発行されたジョブIDと受付ステータス")
async def ocr_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="OCR処理を行いたいPDFファイル"),
    language: str = Query("jpn", description="OCRに使用する言語コード (例: jpn, eng, jpn+eng)"),
    ocr_level: int = Query(4, ge=1, le=5, description="抽出するデータの粒度 (1:ページ, 2:ブロック, 3:段落, 4:行, 5:単語)")
):
    """
    PDFを受け取り、バックグラウンドでのOCR処理を開始してジョブIDを返します。
    処理の進捗確認や結果の取得には、返却された `job_id` を使用してください。
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="PDFファイルのみ対応しています")
    
    # 1. 仕事のユニークなIDを発行（これが呼び出し番号になります）
    job_id = str(uuid.uuid4())
    
    # 2. サーバー内の一次的な場所に保存
    temp_dir = tempfile.mkdtemp()
    pdf_path = Path(temp_dir) / "input.pdf"
    with open(pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # 3. 裏側でOCRを開始するよう「予約」する
    background_tasks.add_task(
        run_ocr_task, 
        job_id, 
        temp_dir, 
        pdf_path, 
        language, 
        file.filename,
        ocr_level
    )
    
    # 4. 「受付完了」を即座に返す
    return {"job_id": job_id, "status": "accepted"}

@app.get("/ocr-status/{job_id}", summary="処理状況の確認")
async def get_status(
    job_id: str = Path(..., description="発行されたジョブID")
):
    """
    指定されたジョブIDの現在のステータス（進行中、完了、失敗など）と進捗率を取得します。
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="仕事が見つかりません。IDが正しいか確認してください。")
    
    return jobs[job_id]

@app.get("/download/{job_id}", summary="検索可能PDFのダウンロード")
async def download_result(
    job_id: str = Path(..., description="発行されたジョブID")
):
    """
    OCR処理が完了した後、テキストレイヤーが埋め込まれた検索可能なPDFファイルをダウンロードします。
    """
    job = jobs.get(job_id)
    if not job or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="まだ処理が完了していないか、IDが正しくありません。")
    
    return FileResponse(
        path=job["result_file"],
        media_type="application/pdf",
        filename=f"searchable_{job['filename']}"
    )

@app.get("/ocr-result-json/{job_id}", summary="構造化JSONデータの取得")
async def get_ocr_result_json(
    job_id: str = Path(..., description="発行されたジョブID")
):
    """
    OCR処理が完了した後、各ページのテキスト・座標・信頼度を含む構造化されたJSONデータを取得します。
    """
    job = jobs.get(job_id)
    if not job or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="まだ処理が完了していないか、IDが正しくありません。")
    
    json_path = Path(job["result_json"])
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="JSON結果ファイルが見つかりません。")
    
    # ファイルを読み取ってJSONとして返す
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data
