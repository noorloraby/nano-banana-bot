# Nano Banana API

Image generation API powered by Google Labs Flow.

## Quick Start

```bash
curl -X POST "https://your-domain.com/generate" \
  -H "X-API-Key: your-api-key" \
  -F "prompt=A futuristic city at sunset" \
  -o output.png
```

## Endpoint

### `POST /generate`

Generate and upscale an image.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | Yes | Image description |
| `aspect_ratio` | string | No | `portrait` or `landscape` |
| `quality` | string | No | `1K` (default), `2K`, `4K` |
| `images` | file(s) | No | Input images for img2img |

**Headers:** `X-API-Key: your-api-key`

**Response:** PNG image binary

## Examples

**Text-to-Image:**
```bash
curl -X POST "https://api.example.com/generate" \
  -H "X-API-Key: secret" \
  -F "prompt=Cyberpunk city" \
  -o image.png
```

**With Quality:**
```bash
curl -X POST "https://api.example.com/generate" \
  -H "X-API-Key: secret" \
  -F "prompt=Mountain landscape" \
  -F "quality=4K" \
  -o image.png
```

**Image-to-Image:**
```bash
curl -X POST "https://api.example.com/generate" \
  -H "X-API-Key: secret" \
  -F "prompt=Transform to oil painting" \
  -F "images=@input.jpg" \
  -o output.png
```

## Response Headers

| Header | Description |
|--------|-------------|
| `X-Upscaled` | `true` or `false` |
| `X-Quality` | Actual quality delivered |
