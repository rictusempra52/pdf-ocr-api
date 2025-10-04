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
    
    try:
        pdf_path = Path(temp_dir) / "input.pdf"
        with open(pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        pages = convert_from_path(str(pdf_path), 300)
        
        tiff_path = Path(temp_dir) / "pages.tif"
        pages[0].save(
            str(tiff_path), 
            "TIFF", 
            compression="tiff_deflate", 
            save_all=True, 
            append_images=pages[1:]
        )
        
        textonly_pdf_base = Path(temp_dir) / "textonly"
        textonly_pdf_path = Path(temp_dir) / "textonly.pdf"
        
        cmd = [
            "tesseract",
            "-c", 'page_separator=[PAGE SEPARATOR]',
            "-c", "textonly_pdf=1",
            str(tiff_path),
            str(textonly_pdf_base),
            "-l", language,
            "pdf"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(
                status_code=500, 
                detail=f"Tesseract OCR failed: {result.stderr}"
            )
        
        output_path = Path(temp_dir) / "output.pdf"
        
        cmd = [
            "qpdf",
            "--overlay", str(textonly_pdf_path),
            "--",
            str(pdf_path),
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"qpdf overlay failed: {result.stderr}"
            )
        
        return FileResponse(
            path=str(output_path),
            media_type="application/pdf",
            filename=f"searchable_{file.filename}",
            background=None
        )
        
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass
