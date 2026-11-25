import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from PIL import Image, ImageOps, UnidentifiedImageError

APP_VERSION = "1.4.0"
app = FastAPI(title="AIToolSathi Media Compression API", version=APP_VERSION)
origins = [
    x.strip()
    for x in os.getenv(
        "ALLOWED_ORIGINS",
        "https://aitoolsathi.in,https://www.aitoolsathi.in",
    ).split(",")
    if x.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "30")) * 1024 * 1024
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
GS = os.getenv("GHOSTSCRIPT_BIN", "gs")
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}

# Existing PDF profiles retained unchanged.
PROFILES = {
    "normal": [(140, 92), (120, 90), (110, 88), (100, 85), (90, 82)],
    "high": [(160, 95), (140, 93), (120, 90), (110, 88), (100, 85), (90, 82)],
}


def _read_image(raw: bytes):
    if not raw:
        raise HTTPException(400, "Please upload a non-empty image.")
    try:
        image = Image.open(io.BytesIO(raw))
        image_format = (image.format or "").upper()
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise HTTPException(415, "Supported formats: JPG, PNG, WEBP, BMP and TIFF.")
        image.load()
        image = ImageOps.exif_transpose(image)
        return image, image_format
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        raise HTTPException(413, f"Image dimensions exceed the {MAX_IMAGE_PIXELS:,}-pixel safety limit.")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "Invalid or damaged image file.")


def _flatten_for_jpeg(image: Image.Image) -> Image.Image:
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _resize_to_fit(image: Image.Image, max_width: int, max_height: int) -> Image.Image:
    if max_width <= 0 and max_height <= 0:
        return image
    width, height = image.size
    scale = min(
        max_width / width if max_width > 0 else 1.0,
        max_height / height if max_height > 0 else 1.0,
        1.0,
    )
    if scale >= 1.0:
        return image
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def _encode_image(image: Image.Image, fmt: str, quality: int, dpi: int):
    buffer = io.BytesIO()
    save_options = {}
    if fmt == "JPEG":
        image = _flatten_for_jpeg(image)
        save_options.update(quality=quality, optimize=True, progressive=True, subsampling=0 if quality >= 90 else 2)
    elif fmt == "WEBP":
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        save_options.update(quality=quality, method=6)
    elif fmt == "PNG":
        save_options.update(optimize=True, compress_level=9)
        if image.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    else:
        save_options.update(optimize=True)
    if dpi > 0:
        save_options["dpi"] = (dpi, dpi)
    image.save(buffer, format=fmt, **save_options)
    return buffer.getvalue()


def _compress_image_bytes(raw: bytes, output_format: str, mode: str, target_kb: int,
                          max_width: int, max_height: int, dpi: int, quality_override: int = 0):
    image, source_format = _read_image(raw)
    fmt = output_format.upper().strip() if output_format else source_format
    aliases = {"JPG": "JPEG"}
    fmt = aliases.get(fmt, fmt)
    if not output_format and fmt not in {"JPEG", "PNG", "WEBP"}:
        fmt = "JPEG"
    if fmt not in {"JPEG", "PNG", "WEBP"}:
        raise HTTPException(400, "Output format must be JPG, PNG or WEBP.")
    if mode not in {"normal", "high"}:
        raise HTTPException(400, "Mode must be normal or high.")
    if not 0 <= dpi <= 1200:
        raise HTTPException(400, "DPI must be between 0 and 1200.")

    image = _resize_to_fit(image, max_width, max_height)
    # Real quality ladder: high mode uses stronger JPEG/WebP compression.
    if quality_override and not 1 <= quality_override <= 95:
        raise HTTPException(400, "Quality must be between 1 and 95, or 0 for automatic mode.")
    qualities = ([quality_override] if quality_override else
                 ([88, 82, 76, 70, 64, 58, 52] if mode == "normal" else [70, 60, 50, 40, 32, 25, 18]))
    if fmt == "PNG":
        # PNG is lossless; quality has no effect. Size reduction comes from
        # optimization and optional dimension limits, not fake quality values.
        candidates = [_encode_image(image, fmt, 100, dpi)]
    else:
        candidates = [_encode_image(image, fmt, q, dpi) for q in qualities]

    target_bytes = target_kb * 1024 if target_kb > 0 else 0
    if target_bytes:
        valid = [data for data in candidates if len(data) <= target_bytes]
        result = valid[0] if valid else min(candidates, key=len)
        target_reached = len(result) <= target_bytes
    else:
        result = candidates[0]
        target_reached = True

    # Never make an in-place/original-format compression larger than its input.
    if fmt == source_format and len(result) >= len(raw):
        result = raw
        target_reached = (not target_bytes) or len(result) <= target_bytes
    return result, fmt, image.size, target_reached


def _image_response(raw: bytes, result: bytes, fmt: str, dimensions, target_reached: bool):
    suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]
    work = Path(tempfile.mkdtemp(prefix="ats-image-"))
    output = work / f"compressed{suffix}"
    output.write_bytes(result)
    media_type = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]
    return FileResponse(
        output,
        media_type=media_type,
        filename=f"compressed{suffix}",
        headers={
            "X-Original-Bytes": str(len(raw)),
            "X-Compressed-Bytes": str(len(result)),
            "X-Target-Reached": "true" if target_reached else "false",
            "X-Image-Width": str(dimensions[0]),
            "X-Image-Height": str(dimensions[1]),
            "X-Output-Format": fmt,
        },
        background=BackgroundTask(shutil.rmtree, work, ignore_errors=True),
    )


@app.get("/")
def root():
    return {
        "service": "AIToolSathi Media Compression API",
        "status": "ok",
        "engines": ["Ghostscript", "Pillow"],
        "version": APP_VERSION,
        "endpoints": ["/compress", "/compress-jpeg", "/compress-image", "/health"],
    }


@app.get("/health")
def health():
    return {
        "ok": True,
        "engines": {"ghostscript": shutil.which(GS) is not None, "pillow": True},
    }


@app.post("/compress")
async def compress_pdf(file: UploadFile = File(...), mode: str = Form("normal"), target_kb: int = Form(0)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Please upload a PDF file.")
    if mode not in ("normal", "high"):
        raise HTTPException(400, "Mode must be normal or high.")
    raw = await file.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413 if len(raw) > MAX_BYTES else 400, f"PDF must be non-empty and under {MAX_BYTES // (1024*1024)} MB.")
    if not raw.startswith(b"%PDF-"):
        raise HTTPException(400, "Invalid PDF file.")
    if not shutil.which(GS):
        raise HTTPException(503, "Ghostscript is not installed on this service.")

    work = Path(tempfile.mkdtemp(prefix="ats-pdf-"))
    src = work / "input.pdf"
    src.write_bytes(raw)
    # pdfwrite rewrites PDF objects instead of rasterizing every page. Selectable text/vector
    # are generally retained; scanned-image pages remain images and may be downsampled.
    if target_kb > 0:
        profiles = ["/screen", "/ebook"] if mode == "normal" else ["/ebook", "/printer"]
    else:
        profiles = ["/printer", "/ebook"] if mode == "normal" else ["/prepress", "/printer"]
    outputs = []
    try:
        for idx, profile in enumerate(profiles):
            out = work / f"output-{idx}.pdf"
            resolution = "96" if profile == "/screen" else ("150" if profile == "/ebook" else ("220" if mode == "high" else "200"))
            cmd = [GS, "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.5", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dQUIET",
                   "-dDetectDuplicateImages=true", "-dCompressFonts=true", "-dSubsetFonts=true", "-dAutoRotatePages=/None",
                   f"-dPDFSETTINGS={profile}", "-dDownsampleColorImages=true", "-dColorImageDownsampleType=/Bicubic",
                   "-dDownsampleGrayImages=true", "-dGrayImageDownsampleType=/Bicubic", "-dDownsampleMonoImages=true",
                   "-dMonoImageDownsampleType=/Subsample", f"-dColorImageResolution={resolution}",
                   f"-dGrayImageResolution={resolution}", "-dMonoImageResolution=300", f"-sOutputFile={out}", str(src)]
            try:
                run = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                continue
            if run.returncode == 0 and out.exists() and out.stat().st_size > 0:
                outputs.append(out)
        if not outputs:
            shutil.rmtree(work, ignore_errors=True)
            raise HTTPException(422, "Could not optimize this PDF. Original file was not changed.")
        # High mode prefers the largest valid Ghostscript output (quality first);
        # normal mode prefers the smallest. Never inflate an already-optimized PDF:
        # if Ghostscript output is larger than the upload, return the original bytes.
        candidate = (max(outputs, key=lambda p: p.stat().st_size) if mode == "high" else min(outputs, key=lambda p: p.stat().st_size))
        if candidate.stat().st_size >= len(raw):
            best = work / "original-preserved.pdf"
            best.write_bytes(raw)
        else:
            best = candidate
        size = best.stat().st_size
        reached = (not target_kb) or size <= target_kb * 1024
        return FileResponse(best, media_type="application/pdf", filename="compressed.pdf",
            headers={"X-Original-Bytes": str(len(raw)), "X-Compressed-Bytes": str(size),
                     "X-Target-Reached": "true" if reached else "false"},
            background=BackgroundTask(shutil.rmtree, work, ignore_errors=True))
    except HTTPException:
        raise
    except Exception as exc:
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(500, "PDF compression failed. Please try another PDF.") from exc


@app.post("/compress-jpeg")
@app.post("/compress_jpeg")
async def compress_jpeg(
    file: UploadFile = File(...),
    mode: str = Form("normal"),
    target_kb: int = Form(0),
    quality: int = Form(0),
    max_width: int = Form(0),
    max_height: int = Form(0),
    dpi: int = Form(0),
):
    if not file.filename or Path(file.filename).suffix.lower() not in {".jpg", ".jpeg"}:
        raise HTTPException(400, "Please upload a JPG or JPEG file.")
    raw = await file.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413 if len(raw) > MAX_BYTES else 400,
                            f"Image must be non-empty and under {MAX_BYTES // (1024 * 1024)} MB.")
    if quality and not 1 <= quality <= 95:
        raise HTTPException(400, "Quality must be between 1 and 95, or 0 for automatic mode.")
    if quality:
        mode = "normal"
    probe, actual_format = _read_image(raw)
    if actual_format != "JPEG":
        raise HTTPException(415, "The uploaded file content is not a JPEG image.")
    result, fmt, dimensions, reached = _compress_image_bytes(raw, "JPEG", mode, target_kb,
                                                               max_width, max_height, dpi)
    if quality:
        image, _ = _read_image(raw)
        image = _resize_to_fit(image, max_width, max_height)
        result = _encode_image(image, "JPEG", quality, dpi)
        if len(result) >= len(raw):
            result = raw
        reached = (target_kb <= 0) or len(result) <= target_kb * 1024
    return _image_response(raw, result, fmt, dimensions, reached)


@app.post("/compress-image")
@app.post("/compress_image")
async def compress_image(
    file: UploadFile = File(...),
    mode: str = Form("normal"),
    target_kb: int = Form(0),
    output_format: str = Form("original"),
    max_width: int = Form(0),
    max_height: int = Form(0),
    dpi: int = Form(0),
    quality: int = Form(0),
):
    if not file.filename:
        raise HTTPException(400, "Please select an image file.")
    raw = await file.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413 if len(raw) > MAX_BYTES else 400,
                            f"Image must be non-empty and under {MAX_BYTES // (1024 * 1024)} MB.")
    output = "" if output_format.lower() == "original" else output_format
    result, fmt, dimensions, reached = _compress_image_bytes(raw, output, mode, target_kb,
                                                               max_width, max_height, dpi, quality)
    return _image_response(raw, result, fmt, dimensions, reached)
