"""BmPriceAgent — drop-in replacement for the docling-price-tables API.

Contract (kept identical so BmBackend needs no changes):
  POST /extract-price-tables  multipart, field "files" (multi) or "file" (single),
                              PDF or ZIP-of-PDFs
      -> {"success": bool,
          "results": [{"fileName", "supplier", "extracted_tables": {filename, producto}}],
          "errors":  [{"fileName", "error"}] (optional)}
      HTTP 200 if at least one file extracted, 400 otherwise.
  GET /health               liveness
  GET /ready                readiness (GEMINI_API_KEY configured)
"""

import io
import logging
import os
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .extractor import PriceExtractor

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("price-agent")

SKILL_DIR = Path(os.environ.get("SKILL_DIR", Path(__file__).resolve().parent.parent / "skill"))
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "5"))
VERSION = "0.1.0"

extractor: PriceExtractor | None = None


def get_extractor() -> PriceExtractor:
    global extractor
    if extractor is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        extractor = PriceExtractor(
            api_key=api_key, model=GEMINI_MODEL,
            skill_dir=SKILL_DIR, max_concurrency=MAX_CONCURRENCY,
        )
    return extractor


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("price-agent %s starting (model=%s, skill=%s)", VERSION, GEMINI_MODEL, SKILL_DIR)
    yield


app = FastAPI(title="bm-price-agent", version=VERSION, lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "price-agent", "version": VERSION,
            "ready": bool(os.environ.get("GEMINI_API_KEY"))}


@app.get("/ready")
async def ready():
    if not os.environ.get("GEMINI_API_KEY"):
        return JSONResponse({"ready": False, "error": "GEMINI_API_KEY is not set"},
                            status_code=503)
    return {"ready": True}


async def process_pdf(pdf_bytes: bytes, filename: str) -> dict:
    payload = await get_extractor().extract(pdf_bytes, filename)
    return {
        "fileName": filename,
        "supplier": payload.get("filename") or "UNKNOWN",
        "extracted_tables": payload,
    }


async def process_upload(filename: str, data: bytes, results: list, errors: list) -> None:
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            if not pdf_names:
                errors.append({"fileName": filename, "error": "ZIP does not contain any PDF files."})
                return
            for inner in pdf_names:
                inner_name = os.path.basename(inner)
                try:
                    results.append(await process_pdf(zf.read(inner), inner_name))
                except Exception as e:
                    logger.exception("error processing %s (from %s)", inner_name, filename)
                    errors.append({"fileName": inner_name, "error": f"Processing error: {e}"})
        return

    if not filename.lower().endswith(".pdf"):
        errors.append({"fileName": filename, "error": "File type not allowed."})
        return
    try:
        results.append(await process_pdf(data, filename))
    except Exception as e:
        logger.exception("error processing %s", filename)
        errors.append({"fileName": filename, "error": f"Processing error: {e}"})


@app.post("/extract-price-tables")
async def extract_price_tables(request: Request):
    return await _handle_extraction(request)


# Legacy provider-specific endpoints, kept as aliases: the agent is format-agnostic,
# so they all run the same extraction. /extract-total is called directly by the
# n8n "Fetch prices from Total" workflow.
@app.post("/extract-total")
@app.post("/extract-adx")
@app.post("/extract-auto")
@app.post("/extract-generic")
async def extract_alias(request: Request):
    return await _handle_extraction(request)


async def _handle_extraction(request: Request):
    form = await request.form()
    uploads = [v for v in form.getlist("files") if hasattr(v, "read")]
    if not uploads:
        uploads = [v for v in form.getlist("file") if hasattr(v, "read")]
    if not uploads:
        return JSONResponse(
            {"success": False, "error": "No file(s) provided in the request."},
            status_code=400)

    results, errors = [], []
    for upload in uploads:
        filename = upload.filename or "uploaded.pdf"
        await process_upload(filename, await upload.read(), results, errors)

    payload = {"success": bool(results), "results": results}
    if errors:
        payload["errors"] = errors
    return JSONResponse(payload, status_code=200 if results else 400)
