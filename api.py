"""
FastAPI server for Nano Banana image generation.
Provides HTTP API access to the same backend used by the Telegram bot.
"""

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Depends, Header
from fastapi.responses import Response
from typing import Optional, List
import asyncio
import logging
import os
import uuid
import io

import config
from browser_client import NanoBananaClient, WebsiteError

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Nano Banana API",
    description="Image generation API using Google Labs Flow",
    version="1.0.0"
)

# Shared browser client (same as Telegram bot uses)
browser_client = NanoBananaClient()

# Lock for serializing browser access (single browser instance)
browser_lock = asyncio.Lock()

# Flag to skip browser init (when run via main.py with shared browser)
SKIP_BROWSER_INIT = os.getenv("SKIP_BROWSER_INIT", "false").lower() == "true"


async def verify_api_key(x_api_key: str = Header(..., description="API Key for authentication")):
    """Dependency to verify API key."""
    if not config.API_KEY:
        raise HTTPException(status_code=500, detail="API_KEY not configured on server")
    if x_api_key != config.API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


@app.on_event("startup")
async def startup_event():
    """Initialize browser on startup (unless managed externally)."""
    if SKIP_BROWSER_INIT:
        logger.info("Skipping browser init (managed externally)")
        return
    logger.info("Starting Nano Banana API server...")
    await browser_client.start()
    logger.info("Browser initialized successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup browser on shutdown (unless managed externally)."""
    if SKIP_BROWSER_INIT:
        logger.info("Skipping browser cleanup (managed externally)")
        return
    logger.info("Shutting down Nano Banana API server...")
    await browser_client.stop()
    logger.info("Browser stopped")


@app.post("/generate", response_class=Response)
async def generate_image(
    prompt: str = Form(..., description="Text prompt for image generation"),
    aspect_ratio: Optional[str] = Form(None, description="Aspect ratio: 'portrait' or 'landscape'"),
    quality: Optional[str] = Form("1K", description="Download quality: '1K', '2K', or '4K'"),
    images: Optional[List[UploadFile]] = File(None, description="Optional input images"),
    _: str = Depends(verify_api_key)
):
    """
    Generate an image from a text prompt with optional input images.
    
    The endpoint will:
    1. Generate image(s) based on the prompt and optional input images
    2. Automatically upscale the first generated image to the requested quality
    3. Return the upscaled (or original if upscale unavailable) image as PNG
    
    - **prompt**: Text description of the image to generate
    - **aspect_ratio**: Optional, 'portrait' or 'landscape' (auto-detected from input images if not specified)
    - **quality**: Download quality - '1K', '2K', or '4K' (default: 2K)
    - **images**: Optional input images for image-to-image generation
    """
    
    # Validate aspect_ratio
    if aspect_ratio and aspect_ratio not in ("portrait", "landscape"):
        raise HTTPException(status_code=400, detail="aspect_ratio must be 'portrait' or 'landscape'")
    
    # Validate quality
    if quality not in ("1K", "2K", "4K"):
        raise HTTPException(status_code=400, detail="quality must be '1K', '2K', or '4K'")
    
    # Process uploaded images (save to temp files like Telegram bot does)
    image_paths = []
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        if images:
            for upload_file in images:
                # Skip empty files
                if not upload_file.filename:
                    continue
                    
                # Determine extension from content type or filename
                ext = "jpg"
                if upload_file.content_type:
                    if "png" in upload_file.content_type:
                        ext = "png"
                    elif "webp" in upload_file.content_type:
                        ext = "webp"
                elif upload_file.filename:
                    file_ext = upload_file.filename.rsplit(".", 1)[-1].lower()
                    if file_ext in ("png", "jpg", "jpeg", "webp"):
                        ext = file_ext
                
                # Save to temp file
                file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")
                content = await upload_file.read()
                with open(file_path, "wb") as f:
                    f.write(content)
                image_paths.append(os.path.abspath(file_path))
                logger.info(f"Saved uploaded image: {file_path}")
        
        # Auto-detect aspect ratio from images if not specified
        if not aspect_ratio and image_paths:
            from PIL import Image, ImageOps
            orientations = []
            for path in image_paths:
                try:
                    with Image.open(path) as img:
                        img = ImageOps.exif_transpose(img)
                        width, height = img.size
                        orientations.append("portrait" if height > width else "landscape")
                except Exception as e:
                    logger.warning(f"Could not analyze image {path}: {e}")
                    orientations.append("landscape")
            
            if orientations and all(o == "portrait" for o in orientations):
                aspect_ratio = "portrait"
                logger.info("Auto-detected portrait aspect ratio from input images")
        
        # Acquire lock for browser access
        async with browser_lock:
            logger.info(f"Processing generation request: prompt='{prompt[:50]}...', aspect={aspect_ratio}, quality={quality}, images={len(image_paths)}")
            
            try:
                # Step 1: Generate images
                generated_images = await browser_client.generate_image(
                    prompt=prompt,
                    image_paths=image_paths if image_paths else None,
                    aspect_ratio=aspect_ratio
                )
                
                if not generated_images:
                    raise HTTPException(status_code=500, detail="No images were generated")
                
                logger.info(f"Generated {len(generated_images)} images, proceeding to upscale")
                
                # Step 2: Upscale the first image to requested quality
                upscaled_stream, used_upscale = await browser_client.upscale_image(
                    prompt=prompt,
                    image_index=0,
                    scale_option=quality
                )
                
                if not upscaled_stream:
                    # Fallback: return the generated image directly
                    logger.warning("Upscale failed, returning generated image")
                    generated_images[0].seek(0)
                    return Response(
                        content=generated_images[0].read(),
                        media_type="image/png",
                        headers={
                            "X-Upscaled": "false",
                            "X-Quality": "original"
                        }
                    )
                
                upscaled_stream.seek(0)
                return Response(
                    content=upscaled_stream.read(),
                    media_type="image/png",
                    headers={
                        "X-Upscaled": str(used_upscale).lower(),
                        "X-Quality": quality if used_upscale else "original"
                    }
                )
                
            except WebsiteError as e:
                logger.error(f"Website error: {e}")
                raise HTTPException(status_code=502, detail=f"Generation service error: {str(e)}")
            
            except Exception as e:
                logger.error(f"Generation failed: {e}")
                raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")
    
    finally:
        # Cleanup temp files
        for path in image_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                    logger.info(f"Cleaned up temp file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {path}: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "browser_ready": browser_client.page is not None
    }


if __name__ == "__main__":
    import uvicorn
    
    port = config.API_PORT
    logger.info(f"Starting Nano Banana API on port {port}")
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
