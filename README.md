# ComicCraft - AI Comic Story Creator using Gemini Models

ComicCraft turns a story idea into a four-panel comic with Gemini, then illustrates it using a Hugging Face image model. Preview and export the finished story as a print-ready, multi-page PDF.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

Open [http://localhost:8000](http://localhost:8000). Gemini generates the story and panel descriptions, so `GEMINI_API_KEY` is required for comic creation. For Hugging Face illustrations, also set `HF_TOKEN`; otherwise ComicCraft uses Gemini image generation and its image quota.

### Configure Hugging Face illustrations

1. Create a fine-grained token at [Hugging Face Access Tokens](https://huggingface.co/settings/tokens) and enable **Make calls to Inference Providers**.
2. Put the token in your local `.env` file. Never commit or share the token:

	```env
	GEMINI_API_KEY=your_gemini_api_key
	HF_TOKEN=hf_your_token
	HF_IMAGE_MODEL=stabilityai/stable-diffusion-3-medium-diffusers
	```

3. Restart the server with `uvicorn main:app --reload`.
4. Open the app, enter a story idea, choose the character, setting, tone, and art style, then select **Make my comic**. ComicCraft generates four panels and their illustrations; **Export comic** downloads them as a PDF.

The selected model and inference-provider access must be available to your Hugging Face account. A token by itself does not enable a model that the provider has retired or does not offer.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `GEMINI_API_KEY` | Google AI Studio API key for Gemini | unset |
| `GEMINI_MODEL` | Gemini text model | `gemini-3.5-flash-lite` |
| `GEMINI_IMAGE_MODEL` | Gemini image-generation model | `gemini-3.1-flash-image` |
| `HF_TOKEN` | Hugging Face token with inference access | unset |
| `HF_IMAGE_MODEL` | Image model served by Hugging Face Inference | `stabilityai/stable-diffusion-3-medium-diffusers` |

The Hugging Face image endpoint uses hosted inference; it does not download model weights or require a local GPU. Model availability and inference quotas depend on the provider account. Gemini and Hugging Face image generation both require an available model quota.

## API

- `GET /api/status` reports which generation providers are configured.
- `POST /api/generate` accepts `prompt`, `character`, `setting`, `tone`, and `style` and returns a comic with panel narration and optional image data.
- `POST /api/export` accepts a comic title and panels and returns a timestamped PDF download.

## Requirements

Python 3.10+, an internet connection for live AI generation, and a modern browser. The demo preview and PDF export work without provider keys.# ComicCraft-