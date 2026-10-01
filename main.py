import asyncio
import base64
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fpdf import FPDF
from PIL import Image
from pydantic import BaseModel, Field

load_dotenv()

ROOT = Path(__file__).parent
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
app = FastAPI(title="ComicCraft - AI Comic Story Creator using Gemini Models")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class ComicRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=1000)
    character: str = Field(default="", max_length=60)
    setting: str = Field(default="", max_length=100)
    tone: str = Field(default="Adventurous", max_length=50)
    style: str = Field(default="Storybook", max_length=50)


class Panel(BaseModel):
    title: str
    narration: str
    image_prompt: str


class Comic(BaseModel):
    title: str
    panels: list[Panel]


class ExportPanel(BaseModel):
    title: str = Field(max_length=120)
    narration: str = Field(max_length=2000)
    image: str | None = Field(default=None, max_length=12_000_000)


class ExportRequest(BaseModel):
    title: str = Field(max_length=120)
    panels: list[ExportPanel] = Field(min_length=1, max_length=6)


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/status")
def status():
    hugging_face = bool(os.getenv("HF_TOKEN"))
    gemini = bool(os.getenv("GEMINI_API_KEY"))
    return {
        "gemini": gemini,
        "images": hugging_face or gemini,
        "image_provider": "Hugging Face" if hugging_face else ("Gemini" if gemini else None),
        "image_model": os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
        if hugging_face else os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_GEMINI_IMAGE_MODEL),
        "model": os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
    }


def _make_story(request: ComicRequest) -> Comic:
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = f"""Create a cohesive, original four-panel comic for a general audience, based on the user's story idea below.
Story idea: {request.prompt}
Main character (if provided): {request.character or "Infer from the story idea"}
Setting (if provided): {request.setting or "Infer from the story idea"}
Tone: {request.tone}
Art style: {request.style}

The story idea is the source of truth. Preserve its premise, named characters, setting, genre, and important details. Do not replace it with a different story or introduce unrelated characters or settings.
Return only JSON with this exact shape:
{{"title":"short comic title","panels":[{{"title":"short panel heading","narration":"1-2 concise sentences of comic narration or dialogue","image_prompt":"visual description for one comic illustration; no text, letters, speech bubbles or watermark"}}]}}
Include exactly four panels. Keep the character and art direction visually consistent across every image_prompt."""
    result = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    payload = json.loads(result.text)
    comic = Comic.model_validate(payload)
    if len(comic.panels) != 4:
        raise ValueError("Gemini did not return exactly four panels.")
    return comic


def _make_gemini_image(image_prompt: str, style: str, topic: str) -> str | None:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    result = client.models.generate_content(
        model=os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_GEMINI_IMAGE_MODEL),
        contents=f"Create one original {style} comic panel illustration based on this story topic: {topic}. Scene: {image_prompt}. No text, lettering, captions, or watermark.",
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
    )
    for part in result.parts or []:
        image = part.inline_data
        if image and image.data:
            mime_type = image.mime_type or "image/png"
            encoded = base64.b64encode(image.data).decode("ascii")
            return f"data:{mime_type};base64,{encoded}"
    return None


def _make_image(image_prompt: str, style: str, topic: str) -> str | None:
    token = os.getenv("HF_TOKEN")
    if not token:
        return _make_gemini_image(image_prompt, style, topic)

    model = os.getenv("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
    try:
        result = requests.post(
            f"https://router.huggingface.co/hf-inference/models/{model}",
            headers={"Authorization": f"Bearer {token}"},
            json={"inputs": f"{style} comic illustration inspired by the story topic: {topic}. Expressive inked lines. Panel scene: {image_prompt}"},
            timeout=90,
        )
        result.raise_for_status()
        if not result.headers.get("content-type", "").startswith("image/"):
            return _make_gemini_image(image_prompt, style, topic)
        image_type = result.headers["content-type"].split(";")[0].split("/")[-1]
        encoded = base64.b64encode(result.content).decode("ascii")
        return f"data:image/{image_type};base64,{encoded}"
    except Exception:
        return _make_gemini_image(image_prompt, style, topic)


@app.post("/api/generate")
async def generate(request: ComicRequest):
    if not os.getenv("GEMINI_API_KEY"):
        raise HTTPException(status_code=503, detail="Add GEMINI_API_KEY to .env to enable Gemini generation.")
    try:
        comic = await asyncio.to_thread(_make_story, request)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Story generation failed: {error}") from error

    images = await asyncio.gather(
        *(
            asyncio.to_thread(_make_image, panel.image_prompt, request.style, request.prompt)
            for panel in comic.panels
        ),
        return_exceptions=True,
    )
    image_errors = [image for image in images if isinstance(image, Exception)]
    image_warning = None
    if image_errors:
        details = " ".join(str(error) for error in image_errors)
        if "RESOURCE_EXHAUSTED" in details or "429" in details:
            image_warning = "Image quota exceeded. Enable Gemini image billing or configure HF_TOKEN for illustrations."
        elif "PERMISSION_DENIED" in details or "403" in details:
            image_warning = "Gemini image generation is not enabled for this account. Enable image access or configure HF_TOKEN."
        else:
            image_warning = "Illustrations could not be generated. Check image-model access or configure HF_TOKEN."
    panels = []
    for panel, image in zip(comic.panels, images):
        panel_data = panel.model_dump()
        panel_data["image"] = image if isinstance(image, str) else None
        panel_data["image_error"] = isinstance(image, Exception) or image is None
        panels.append(panel_data)
    return {"title": comic.title, "panels": panels, "image_warning": image_warning}


def _pdf_text(text: str) -> str:
    return re.sub(r"[^\x00-\xff]", "?", text)


def _pdf_image(image: str | None) -> io.BytesIO | None:
    if not image:
        return None
    if image.startswith("data:image/") and "," in image:
        try:
            _, encoded = image.split(",", 1)
            image_bytes = base64.b64decode(encoded, validate=True)
        except ValueError:
            return None
    else:
        parsed = urlsplit(image)
        if parsed.scheme != "https" or parsed.hostname != "images.unsplash.com" or parsed.port not in (None, 443):
            return None
        try:
            response = requests.get(image, timeout=15, allow_redirects=False, stream=True)
            response.raise_for_status()
            if not response.headers.get("content-type", "").startswith("image/"):
                return None
            image_bytes = response.content
        except requests.RequestException:
            return None
    if len(image_bytes) > 10_000_000:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            if source.width * source.height > 24_000_000:
                return None
            result = io.BytesIO()
            source.convert("RGB").save(result, format="PNG")
            result.name = "panel.png"
            result.seek(0)
            return result
    except (OSError, Image.DecompressionBombError):
        return None


@app.post("/api/export")
def export_comic(request: ExportRequest):
    pdf = FPDF(format="A4")
    pdf.set_title(_pdf_text(request.title))
    for index, panel in enumerate(request.panels, start=1):
        pdf.add_page()
        pdf.set_margins(16, 18, 16)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(50, 111, 95)
        pdf.cell(0, 8, _pdf_text(f"COMICCRAFT  /  PANEL {index:02d}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_text_color(28, 39, 38)
        pdf.set_font("Helvetica", "B", 26)
        pdf.multi_cell(0, 12, _pdf_text(panel.title))
        stream = _pdf_image(panel.image)
        if stream:
            pdf.image(stream, x=16, y=pdf.get_y() + 5, w=178, h=112, keep_aspect_ratio=True)
            pdf.set_y(pdf.get_y() + 121)
        pdf.ln(5)
        pdf.set_font("Helvetica", size=14)
        pdf.set_text_color(55, 64, 61)
        pdf.multi_cell(0, 8, _pdf_text(panel.narration))
    filename = f"comiccraft-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.pdf"
    return Response(
        content=bytes(pdf.output()),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )