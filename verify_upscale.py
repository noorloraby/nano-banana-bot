import asyncio
import logging
from browser_client import NanoBananaClient

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_upscale():
    client = NanoBananaClient()
    await client.start()
    
    try:
        prompt = "a blue cube"
        logger.info(f"Testing generation for: {prompt}")
        
        # 1. Generate
        images = await client.generate_image(prompt)
        if not images:
            logger.error("Generation failed, no images returned.")
            return

        logger.info(f"Generated {len(images)} images.")
        
        # 2. Upscale the first one
        logger.info("Testing upscale for index 0...")
        upscaled_stream = await client.upscale_image(prompt, 0, "2K")
        
        if upscaled_stream:
            size = upscaled_stream.getbuffer().nbytes
            logger.info(f"Upscale successful! Got {size} bytes.")
            with open("test_upscaled_result.png", "wb") as f:
                f.write(upscaled_stream.getbuffer())
        else:
            logger.error("Upscale returned None.")

    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.stop()

if __name__ == "__main__":
    asyncio.run(test_upscale())
