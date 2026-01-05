import asyncio
from playwright.async_api import async_playwright
# from playwright_stealth import stealth_async
import logging

# Basic logging setup for standalone test
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("StealthTest")

async def test_stealth():
    from browser_client import NanoBananaClient
    logger.info("Launching NanoBananaClient...")
    
    client = NanoBananaClient()
    await client.start()
    page = client.page
    
    # Test 1: Sannysoft Bot Test (Optional, commented out)
    # logger.info("Navigating to bot detection test site...")
    # await page.goto("https://bot.sannysoft.com/")
    # await page.screenshot(path="stealth_report.png", full_page=True)
    # logger.info("Saved stealth_report.png")

    # Test 2: The Target URL
    target_url = client.target_url
    logger.info(f"Navigating to target: {target_url}")
    
    # client.start() already navigates, so we check content
    content = await page.content()
    
    if "403 Forbidden" in content or "Access Denied" in content:
        logger.error("FAILED: Received 403 Forbidden/Access Denied.")
    else:
        logger.info("SUCCESS: No 403 error detected in page content.")
        
    await asyncio.sleep(5) 
    await client.stop()

if __name__ == "__main__":
    asyncio.run(test_stealth())
