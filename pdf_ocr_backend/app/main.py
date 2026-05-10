from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pyocr
import pyocr.builders
from pdf2image import convert_from_path
import subprocess
import os
import tempfile
import shutil
from pathlib import Path

import logging

# ログの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PDF OCR API", description="Convert scanned PDFs to searchable PDFs using OCR")

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {
        "message": "PDF OCR API",
        "endpoints": {
            "/ocr-pdf": "POST - Upload a PDF file to convert it to searchable PDF",
            "/healthz": "GET - Health check"
        }
    }

@app.post("/ocr-pdf")
async def ocr_pdf(
    file: UploadFile = File(...),
    language: str = "jpn"
):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    valid_languages = ["jpn", "eng", "jpn+eng"]
    if language not in valid_languages:
        raise HTTPException(
            status_code=400, 
            detail=f"Language must be one of: {', '.join(valid_languages)}"
        )
    
    tools = pyocr.get_available_tools()
    if len(tools) == 0:
        raise HTTPException(status_code=500, detail="No OCR tool found")
    
    tool = tools[0]
    
    temp_dir = tempfile.mkdtemp()
    logger.info(f"作業ディレクトリを作成しました: {temp_dir}")
    
    try:
        pdf_path = Path(temp_dir) / "input.pdf"
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"ファイルを保存しました: {file.filename}")
        
        # 1ページずつ画像に変換して保存
        output_images_dir = Path(temp_dir) / "images"
        output_images_dir.mkdir()
        
        logger.info("PDFを画像に変換中...")
        # メモリ節約のため、ディスクに直接書き出す
        image_paths = convert_from_path(
            str(pdf_path), 
            300, 
            output_folder=str(output_images_dir),
            fmt="tiff",
            paths_only=True
        )
        
        total_pages = len(image_paths)
        logger.info(f"全 {total_pages} ページの画像変換が完了しました。")
        
        textonly_pdfs = []
        for i, img_path in enumerate(image_paths):
            page_num = i + 1
            logger.info(f"[{page_num}/{total_pages}] ページのOCR処理を開始します...")
            
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
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Tesseract エラー (ページ {page_num}): {result.stderr}")
                raise HTTPException(status_code=500, detail=f"Tesseract OCR failed on page {page_num}")
            
            textonly_pdfs.append(str(page_pdf))
            
        logger.info("全ページのOCR処理が完了しました。PDFを結合中...")
        
        # 全てのテキストPDFを1つに結合
        combined_textonly_pdf = Path(temp_dir) / "combined_textonly.pdf"
        cmd = ["qpdf", "--empty", "--pages"] + textonly_pdfs + ["--", str(combined_textonly_pdf)]
        subprocess.run(cmd, check=True)
        
        # 元のPDFにテキスト層を重ねる
        output_path = Path(temp_dir) / "output.pdf"
        cmd = [
            "qpdf",
            "--overlay", str(combined_textonly_pdf),
            "--",
            str(pdf_path),
            str(output_path)
        ]
        
        logger.info("最終的なPDFを作成中...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"qpdf エラー: {result.stderr}")
            raise HTTPException(status_code=500, detail="qpdf overlay failed")
        
        logger.info("処理が正常に完了しました。ファイルを送信します。")
        
        return FileResponse(
            path=str(output_path),
            media_type="application/pdf",
            filename=f"searchable_{file.filename}",
            background=None
        )
        
    except Exception as e:
        logger.exception("予期しないエラーが発生しました")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 非同期で削除するとエラーになることがあるため、ここでは何もしないか、
        # 必要に応じて定期的なクリーンアップジョブを検討する。
        # (FileResponseがファイルを読み終わる前に削除してはいけないため)
        pass
