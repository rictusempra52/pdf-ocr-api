import logging
import uuid
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import pyocr
import pyocr.builders
from pdf2image import convert_from_path
import subprocess
import os
import tempfile
import shutil
from pathlib import Path

# --- 1. 準備：ログと進捗管理の設定 ---

# ログの設定（プログラムの動きを日本語で出力するようにします）
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 進捗管理ノート（辞書型）
# 構造: jobs[job_id] = {"status": "進行中", "progress": 50, "result_file": "path", "filename": "..."}
jobs = {}

# 完成したファイルを一時保存する場所
RESULTS_DIR = Path(tempfile.gettempdir()) / "ocr_results"
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

# --- 2. バックグラウンドで行う重い処理（OCR本体） ---

def run_ocr_task(job_id: str, temp_dir: str, pdf_path: Path, language: str, original_filename: str):
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
        
        # 1ページずつOCRを実行
        for i, img_path in enumerate(image_paths):
            page_num = i + 1
            
            # ノートの進捗率を更新
            progress_percent = int((i / total_pages) * 100)
            jobs[job_id]["progress"] = progress_percent
            logger.info(f"[{job_id}] 進行状況: {page_num}/{total_pages} ページ目を処理中 ({progress_percent}%)")
            
            page_base = Path(temp_dir) / f"page_{page_num}"
            page_pdf = Path(temp_dir) / f"page_{page_num}.pdf"
            
            cmd = [
                "tesseract",
                "-c", "textonly_pdf=1",
                str(img_path),
                str(page_base),
                "-l", language,
                "pdf"
            ]
            
            subprocess.run(cmd, check=True)
            textonly_pdfs.append(str(page_pdf))
            
        logger.info(f"[{job_id}] 全ページのOCRが完了。結合中...")
        
        # 完了したPDFを作成
        combined_text_pdf = Path(temp_dir) / "combined.pdf"
        subprocess.run(["qpdf", "--empty", "--pages"] + textonly_pdfs + ["--", str(combined_text_pdf)], check=True)
        
        final_output_path = RESULTS_DIR / f"{job_id}.pdf"
        subprocess.run([
            "qpdf", "--overlay", str(combined_text_pdf), "--", 
            str(pdf_path), str(final_output_path)
        ], check=True)
        
        # ノートを「完了」に書き換える
        jobs[job_id].update({
            "status": "completed",
            "progress": 100,
            "result_file": str(final_output_path)
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

@app.post("/ocr-pdf")
async def ocr_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: str = "jpn"
):
    """
    【注文口】PDFを受け取り、すぐに受付番号(Job ID)を返します。
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
        file.filename
    )
    
    # 4. 「受付完了」を即座に返す
    return {"job_id": job_id, "status": "accepted"}

@app.get("/ocr-status/{job_id}")
async def get_status(job_id: str):
    """
    【確認口】「私の番号、今どうなってる？」と聞くための場所。
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="仕事が見つかりません。IDが正しいか確認してください。")
    
    return jobs[job_id]

@app.get("/download/{job_id}")
async def download_result(job_id: str):
    """
    【受取口】完了したPDFをダウンロードするための場所。
    """
    job = jobs.get(job_id)
    if not job or job["status"] != "completed":
        raise HTTPException(status_code=400, detail="まだ処理が完了していないか、IDが正しくありません。")
    
    return FileResponse(
        path=job["result_file"],
        media_type="application/pdf",
        filename=f"searchable_{job['filename']}"
    )
