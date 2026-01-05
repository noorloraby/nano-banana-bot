import asyncio
import io
from playwright.async_api import async_playwright, BrowserContext
# from playwright_stealth import stealth_async
import logging
import config

logger = logging.getLogger(__name__)

class WebsiteError(Exception):
    """Raised when the website displays an error or warning toast."""
    pass

class NanoBananaClient:
    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        # Specific target URL provided by user
        self.target_url = "https://labs.google/fx/tools/flow/project/feaf1427-a157-4a61-be71-62b4677ec225"

    async def start(self):
        """Initializes the browser with persistent context and stealth settings."""
        logger.info(f"Starting Nano Banana Client with Stealth (Persistent: {config.USER_DATA_DIR})...")
        self.playwright = await async_playwright().start()
        
        # Detect if running in Docker/Linux
        import platform
        is_linux = platform.system() == "Linux"
        
        # Use appropriate user agent for the platform
        if is_linux:
            user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        else:
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-infobars', 
            '--window-size=1280,800',
            '--disable-features=IsolateOrigins,site-per-process',
            # Additional anti-detection args
            '--disable-dev-shm-usage',
            '--disable-background-networking',
            '--disable-default-apps',
            '--disable-extensions',
            '--disable-sync',
            '--disable-translate',
            '--hide-scrollbars',
            '--metrics-recording-only',
            '--mute-audio',
            '--no-first-run',
            '--safebrowsing-disable-auto-update',
            # Important for headless detection bypass
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
            '--disable-background-timer-throttling',
            '--disable-ipc-flooding-protection',
            '--enable-features=NetworkService,NetworkServiceInProcess',
        ]

        # Use chromium by default, but launch_persistent_context
        # Note: launch_persistent_context launches a browser instance that persists to user_data_dir
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=config.USER_DATA_DIR,
            channel="chrome",  # Use installed chrome for better stealth
            headless=config.HEADLESS,
            args=args,
            user_agent=user_agent,
            viewport={'width': 1280, 'height': 800},
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            geolocation={'latitude': 40.71, 'longitude': -74.00},
            ignore_default_args=['--enable-automation'],  # Critical: disable automation flag
        )
        
        # In persistent context, pages might already exist (e.g. from previous session restore), 
        # or we might need to create one. Usually the first page is opened.
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        # Attempt to use playwright-stealth, fallback to manual scripts
        stealth_applied = False
        try:
            # Try imports based on investigation
            try:
                from playwright_stealth import stealth_async
                await stealth_async(self.page)
                stealth_applied = True
                logger.info("Applied playwright-stealth via stealth_async")
            except ImportError:
                 # Try usage of Stealth class if available or just skip
                 pass
        except Exception as e:
            logger.warning(f"Could not apply playwright-stealth: {e}")

        if not stealth_applied:
            logger.info("Applying manual stealth scripts...")
            # Comprehensive stealth scripts for Linux/Docker
            await self.page.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                
                // Fix navigator.plugins (empty in headless)
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
                        { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
                    ]
                });
                
                // Fix navigator.languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                
                // Mock chrome runtime
                window.chrome = {
                    runtime: {
                        connect: () => {},
                        sendMessage: () => {},
                        onMessage: { addListener: () => {} }
                    },
                    loadTimes: () => ({
                        commitLoadTime: Date.now() / 1000,
                        connectionInfo: 'http/1.1',
                        finishDocumentLoadTime: Date.now() / 1000,
                        finishLoadTime: Date.now() / 1000,
                        firstPaintAfterLoadTime: 0,
                        firstPaintTime: Date.now() / 1000,
                        navigationType: 'Other',
                        npnNegotiatedProtocol: 'unknown',
                        requestTime: Date.now() / 1000,
                        startLoadTime: Date.now() / 1000,
                        wasAlternateProtocolAvailable: false,
                        wasFetchedViaSpdy: false,
                        wasNpnNegotiated: false
                    }),
                    csi: () => ({ startE: Date.now(), onloadT: Date.now(), pageT: Date.now(), tran: 15 })
                };
                
                // Fix permissions query
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
                );
                
                // Fix WebGL vendor/renderer (common detection method)
                const getParameterProxyHandler = {
                    apply: function(target, ctx, args) {
                        const param = args[0];
                        const result = Reflect.apply(target, ctx, args);
                        // UNMASKED_VENDOR_WEBGL
                        if (param === 37445) return 'Google Inc. (NVIDIA)';
                        // UNMASKED_RENDERER_WEBGL
                        if (param === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 6GB Direct3D11 vs_5_0 ps_5_0, D3D11)';
                        return result;
                    }
                };
                const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = new Proxy(originalGetParameter, getParameterProxyHandler);
            """)

        logger.info("Browser started successfully.")
        
        # Human-like initial navigation
        # Strategy: First go to Google (as a stepping stone), then navigate to target
        # This is more natural than going directly from about:blank
        try:
            import random
            
            # Add random human-like delay (1-3 seconds)
            delay = random.uniform(1.5, 3.0)
            await asyncio.sleep(delay)
            
            logger.info(f"Navigating to {self.target_url}")
            
            # Step 1: First navigate to Google as a stepping stone
            # This is less suspicious than going directly from about:blank
            try:
                await self.page.goto(
                    "https://www.google.com",
                    wait_until="domcontentloaded",
                    timeout=15000
                )
                await asyncio.sleep(random.uniform(1.0, 2.0))
                logger.info("Arrived at Google, now navigating to target...")
            except Exception as e:
                logger.warning(f"Could not navigate to Google first: {e}")
            
            # Step 2: Now navigate to target using keyboard (more human-like)
            try:
                # Focus the page first
                await self.page.bring_to_front()
                
                # Use Ctrl+L to focus address bar, then type URL
                await self.page.keyboard.press("Control+l")
                await asyncio.sleep(random.uniform(0.3, 0.6))
                
                # Type the URL with human-like delays
                await self.page.keyboard.type(self.target_url, delay=random.randint(20, 50))
                await asyncio.sleep(random.uniform(0.2, 0.4))
                
                # Press Enter to navigate
                await self.page.keyboard.press("Enter")
                
                # Wait for navigation to complete
                await self.page.wait_for_load_state("networkidle", timeout=30000)
                logger.info("Navigation completed via keyboard method")
                
            except Exception as kb_error:
                logger.warning(f"Keyboard navigation failed: {kb_error}, falling back to goto with referrer")
                
                # Fallback - use goto with realistic referrer
                await self.page.goto(
                    self.target_url,
                    referer="https://www.google.com/",
                    wait_until="networkidle"
                )
                
        except Exception as e:
            logger.error(f"Failed initial navigation: {e}")

    async def stop(self):
        """Closes the browser."""
        logger.info("Stopping browser client...")
        try:
            if self.context:
                await self.context.close()
        except Exception as e:
            logger.debug(f"Error closing context: {e}")
            
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error stopping playwright: {e}")
            
        logger.info("Browser stopped.")

    async def _refresh_page(self):
        """Refreshes the page and waits for it to load."""
        if not self.page:
            return
        
        try:
            logger.info("Refreshing page...")
            await self.page.reload(wait_until="networkidle")
            await asyncio.sleep(2)  # Wait for UI to settle
            logger.info("Page refreshed successfully")
        except Exception as e:
            logger.error(f"Failed to refresh page: {e}")

    async def _check_for_inline_generation_error(self) -> tuple[bool, str | None]:
        """Check for inline generation errors (e.g., 'Something went wrong.' displayed in result area).
        This is different from toast errors - it appears inside the image generation result container.
        Returns (has_error, error_message)."""
        if not self.page:
            return (False, None)
        
        try:
            # Look for the error message pattern shown in the HTML structure
            # The error appears in a div with specific text content
            error_divs = self.page.locator('div').filter(has_text="Something went wrong.")
            
            count = await error_divs.count()
            if count > 0:
                # Verify it's the actual error message, not just any div containing this text
                for i in range(count):
                    div = error_divs.nth(i)
                    try:
                        text = await div.inner_text()
                        # Check if this div is the actual error message (text should be exactly or very close to the error)
                        if text.strip() == "Something went wrong.":
                            logger.warning("Detected inline generation error: Something went wrong.")
                            return (True, "Something went wrong.")
                    except:
                        pass
        except Exception as e:
            logger.debug(f"Error checking for inline generation error: {e}")
        
        return (False, None)

    async def _check_for_toast_error(self) -> tuple[bool, str | None]:
        """Check for error/warning toast messages on the page.
        Returns (has_error, error_message).
        Automatically refreshes the page if 'Something went wrong' is detected."""
        if not self.page:
            return (False, None)
        
        try:
            # Look for any visible sonner toast
            all_toasts = self.page.locator('li[data-sonner-toast][data-visible="true"]')
            
            toast_count = await all_toasts.count()
            if toast_count > 0:
                for i in range(toast_count):
                    toast = all_toasts.nth(i)
                    
                    # Check if this toast contains an error icon
                    # The error icon is an <i> element with text content "error"
                    error_icon = toast.locator('i').filter(has_text="error")
                    
                    if await error_icon.count() > 0:
                        # This is an error toast - extract the message
                        message = None
                        
                        # Try data-title div first
                        title_el = toast.locator('[data-title]')
                        if await title_el.count() > 0:
                            message = await title_el.inner_text()
                        
                        # If no title, try data-content
                        if not message:
                            content_el = toast.locator('[data-content]')
                            if await content_el.count() > 0:
                                message = await content_el.inner_text()
                        
                        # Fallback: get inner text of the whole toast
                        if not message:
                            message = await toast.inner_text()
                        
                        # Clean up the message
                        if message:
                            message = message.strip()
                            # Remove any "error" icon text that might be included
                            if message.startswith("error"):
                                message = message[5:].strip()
                        
                        logger.info(f"Detected error toast: {message}")
                        
                        # Auto-refresh on "Something went wrong" error
                        if message and "Something went wrong" in message:
                            logger.warning("Detected 'Something went wrong' error - refreshing page...")
                            await self._refresh_page()
                        
                        return (True, message or "Unknown error from website")
                
        except Exception as e:
            logger.debug(f"Error checking for toast: {e}")
        
        return (False, None)

    async def _clear_prompt_and_images(self):
        """Clears the prompt textarea and removes all uploaded images to reset state."""
        if not self.page:
            return
        
        try:
            # Clear the prompt textarea
            prompt_input = self.page.locator("textarea#PINHOLE_TEXT_AREA_ELEMENT_ID")
            if await prompt_input.count() > 0:
                await prompt_input.fill("")
                logger.info("Cleared prompt textarea")
        except Exception as e:
            logger.warning(f"Failed to clear prompt: {e}")
        
        try:
            # Find and click all close buttons on uploaded images
            # These are buttons with a "close" icon
            close_buttons = self.page.locator("button").filter(
                has=self.page.locator("i", has_text="close")
            )
            
            count = await close_buttons.count()
            if count > 0:
                logger.info(f"Removing {count} uploaded images...")
                # Click each close button (in reverse to avoid index shifting issues)
                for i in range(count - 1, -1, -1):
                    try:
                        btn = close_buttons.nth(i)
                        if await btn.is_visible():
                            await btn.click()
                            await asyncio.sleep(0.3)  # Brief pause between removals
                    except Exception as e:
                        logger.debug(f"Failed to click close button {i}: {e}")
                
                logger.info("Removed uploaded images")
        except Exception as e:
            logger.warning(f"Failed to clear images: {e}")
        
        # Wait for UI to settle
        await asyncio.sleep(0.5)

    async def generate_image(self, prompt: str, image_paths: list = None):
        """
        Generates an image from a text prompt and optional image inputs.
        """
        if not self.page:
            # Try to recover or just fail
            raise RuntimeError("Browser not started")

        logger.info(f"Attempting to generate image for prompt: {prompt} (Images: {len(image_paths) if image_paths else 0})")
        
        # Verification check - are we forbidden?
        try:
            content = await self.page.content()
            if "403 Forbidden" in content or "Access Denied" in content:
                logger.error("Still detected as bot (403 Forbidden).")
                raise Exception("Access Denied by Google Labs")
        except Exception as e:
             # If page is closed, this might fail
             logger.error(f"Error checking page content: {e}")
             raise

        # 1. Switch to Images mode if needed
        try:
            # Check if Images button is selected
            images_btn = self.page.get_by_role("radio", name="Images")
            if await images_btn.count() > 0:
                is_checked = await images_btn.get_attribute("aria-checked")
                if is_checked != "true":
                    logger.info("Switching to Images mode...")
                    await images_btn.click()
                    await asyncio.sleep(1) # Wait for switch
        except Exception as e:
            logger.warning(f"Failed to switch to Images mode (might already be in correct mode or selector changed): {e}")

        # 2. Enter prompt (Now done BEFORE uploads as requested)
        try:
            prompt_input = self.page.locator("textarea#PINHOLE_TEXT_AREA_ELEMENT_ID")
            await prompt_input.fill(prompt)
            logger.info("Filled prompt")
        except Exception as e:
            logger.error(f"Failed to find prompt input: {e}")
            raise

        # 1.5 Handle Image Uploads
        if image_paths:
            logger.info(f"Uploading {len(image_paths)} images: {image_paths}")
            for idx, img_path in enumerate(image_paths):
                try:
                    logger.info(f"Uploading image {idx+1}/{len(image_paths)}: {img_path}")
                    
                    # 1. Click the main "Add" prompt image button (the plus icon)
                    # We use a strict selector to avoid clicking the "Close" button of existing images
                    # Strategy: Get all buttons that have an 'add' icon, excluding those with 'close' icon
                    # The user provided HTML shows specific classes but we stick to structure for robustness.
                    
                    # Wait for any potential animations
                    await asyncio.sleep(1)

                    add_btn_locator = self.page.locator("button").filter(
                        has=self.page.locator("i", has_text="add")
                    ).filter(
                        has_not=self.page.locator("i", has_text="close")
                    ).last

                    # Verify we found it
                    if await add_btn_locator.count() == 0:
                        logger.warning("Could not find 'Add' button with 'add' icon. Dumping debug info...")
                        # Fallback try less strict
                        add_btn_locator = self.page.locator("button").filter(has=self.page.locator("i", has_text="add")).last

                    await add_btn_locator.wait_for(state="visible", timeout=5000)
                    
                    # Ensure we are not clicking something disabled
                    # await add_btn.wait_for(state="enabled") # Optional
                    
                    await add_btn_locator.click()
                    logger.info("Clicked Add button")
                    await asyncio.sleep(1)

                    # Get current count of uploaded images to wait for change
                    # Uploaded images are identified by having a "close" icon
                    uploaded_items_locator = self.page.locator("button").filter(has=self.page.locator("i", has_text="close"))
                    initial_count = await uploaded_items_locator.count()
                    logger.info(f"Current uploaded images count: {initial_count}")

                    # 2. Click the specific "Upload" button
                    # User provided HTML shows the Upload button is in a container with data-index="0".
                    # We target this specifically to avoid clicking any gallery images (which would be at index 1+).
                    upload_btn = self.page.locator('div[data-index="0"] button').filter(
                        has=self.page.locator("i", has_text="upload")
                    ).filter(
                        has_text="Upload"
                    ).first
                    
                    # Wait for it to appear
                    await upload_btn.wait_for(state="visible", timeout=5000)
                    
                    # Start waiting for file chooser before clicking "Upload"
                    async with self.page.expect_file_chooser() as fc_info:
                        await upload_btn.click()
                    
                    file_chooser = await fc_info.value
                    await file_chooser.set_files([img_path]) # Set single file
                    logger.info(f"File selected: {img_path}")
                    
                    # 3. Handle "Crop and Save"
                    crop_save_btn = self.page.get_by_role("button", name="Crop and Save")
                    try:
                        await crop_save_btn.wait_for(state="visible", timeout=10000)
                        await crop_save_btn.click()
                        logger.info("Clicked Crop and Save")
                    except Exception as e:
                        logger.warning(f"Crop and Save button not found or timed out: {e}")

                    # Wait for upload to process (dynamic wait)
                    logger.info("Waiting for upload to complete (count increase)...")
                    try:
                        # Poll for count increase
                        # We use a loop because simple explicit waits for count can be tricky without assertions library
                        # or we can use wait_for_function
                        
                        async def check_count():
                            current = await uploaded_items_locator.count()
                            return current > initial_count
                        
                        # Custom poll
                        max_retries = 60 # 60 seconds max
                        uploaded = False
                        for _ in range(max_retries):
                            # Check for error toasts first
                            has_error, error_msg = await self._check_for_toast_error()
                            if has_error:
                                logger.error(f"Website error during upload: {error_msg}")
                                await self._clear_prompt_and_images()
                                raise WebsiteError(error_msg)
                            
                            if await check_count():
                                uploaded = True
                                break
                            await asyncio.sleep(1)
                        
                        if not uploaded:
                            logger.warning("Upload count did not increase within timeout.")
                        else:
                            logger.info("Upload confirmed (count increased).")
                            
                        # Small buffer for UI settlement
                        await asyncio.sleep(1)

                    except WebsiteError:
                        raise  # Re-raise WebsiteError
                    except Exception as e:
                         logger.error(f"Error waiting for upload completion: {e}")

                    
                except Exception as e:
                    logger.error(f"Failed to upload image {img_path}: {e}")
                    # Continue to next image

        # 3. Click Create
        try:
            # Wait a bit for validation/button enablement
            await asyncio.sleep(0.5)
            create_btn = self.page.get_by_role("button", name="Create")
            # Ensure it's enabled
            await create_btn.wait_for(state="visible")
            if await create_btn.is_disabled():
                 logger.warning("Create button is disabled, trying to wait...")
                 await create_btn.wait_for(state="enabled", timeout=5000)
            
            await create_btn.click()
            logger.info("Clicked Create button")
        except Exception as e:
            logger.error(f"Failed to click Create button: {e}")
            raise

        # 4. Wait for generation
        logger.info("Waiting for generation result...")
        
        # Strategy: 
        # 1. Find all images where alt text contains the prompt (Robust filtering).
        # 2. Compare 'src' attributes before and after to strictly identify NEW images.
        # This handles repeated prompts and ordering (prepend vs append) correctly.

        try:
             # Capture initial state
             initial_data = await self._find_images_by_prompt_matches(prompt)
             initial_srcs = set(item["src"] for item in initial_data)
             logger.info(f"Initial matching images count: {len(initial_data)}")

             # Wait loop
             import time
             start_time = time.time()
             max_wait = config.TIMEOUT_MS / 1000
             
             new_items = []
             
             while time.time() - start_time < max_wait:
                 # Check for error toasts first
                 has_error, error_msg = await self._check_for_toast_error()
                 if has_error:
                     logger.error(f"Website error during generation: {error_msg}")
                     await self._clear_prompt_and_images()
                     raise WebsiteError(error_msg)
                 
                 # Check for inline generation errors (e.g., "Something went wrong." in result area)
                 has_inline_error, inline_error_msg = await self._check_for_inline_generation_error()
                 if has_inline_error:
                     logger.error(f"Inline generation error detected: {inline_error_msg}")
                     await self._refresh_page()
                     await self._clear_prompt_and_images()
                     raise WebsiteError(inline_error_msg)
                 
                 current_data = await self._find_images_by_prompt_matches(prompt)
                 
                 # Identify new SRCs
                 potential_new = [item for item in current_data if item["src"] not in initial_srcs]
                 
                 # We expect usually 2 images
                 if len(potential_new) >= 2:
                     new_items = potential_new
                     # Small settlement wait
                     await asyncio.sleep(2)
                     break
                 
                 if len(potential_new) >= 1:
                     # Check if we waited long enough for a second one?
                     # Let's wait a bit more aggressively if we have at least one
                     if not new_items:
                         # Use this as current best candidate
                         new_items = potential_new
                         logger.info("Found 1 image, waiting for potential second...")
                     else:
                         # We already had candidates, update if we found more
                         if len(potential_new) > len(new_items):
                             new_items = potential_new
                 
                 await asyncio.sleep(1)

             if not new_items:
                 logger.error("Timeout: No new images matches found.")
                 raise Exception("Generation Timed Out - No images found matching prompt")

             logger.info(f"Found {len(new_items)} new images.")

             # Capture images
             new_image_streams = []
             import io

             for item in new_items:
                 img = item["element"]
                 src = item["src"]
                 
                 try:
                     # Wait for visible
                     await img.wait_for(state="visible", timeout=5000)
                     await img.scroll_into_view_if_needed()
                     
                     logger.info(f"Capturing new image: {src[:50]}...")
                     data = await img.screenshot(type="png")
                     new_image_streams.append(io.BytesIO(data))
                 except Exception as e:
                     logger.error(f"Failed to capture image {src[:30]}: {e}")

             return new_image_streams


        except Exception as e:
            logger.error(f"Failed to wait/capture result: {e}")
            # Fallback: Dump page again for debugging if failed
            try:
                html = await self.page.content()
                with open("debug_page_dump_failed_v2.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except: pass
            raise Exception("Generation Timed Out or Failed")

    async def _find_images_by_prompt_matches(self, prompt: str):
        """Helper to find all matching image elements and their SRCs for a given prompt."""
        if not self.page:
            return []
            
        # We look for images with "Flow Image" first to narrow down
        candidates = await self.page.locator('img[alt*="Flow Image"]').all()
        matches = []
        for img in candidates:
            try:
                alt = await img.get_attribute("alt")
                src = await img.get_attribute("src")
                # Check if prompt is in alt
                if alt and prompt in alt:
                    matches.append({"element": img, "src": src})
            except:
                pass # Element might have detached
        return matches

    async def upscale_image(self, prompt: str, image_index: int, scale_option: str):
        """
        Upscales an image (identified by prompt and index) using the specified option (1K, 2K, 4K).
        Returns the downloaded file bytes.
        """
        logger.info(f"Attempting to upscale image {image_index} for prompt '{prompt}' to {scale_option}")
        
        matches = await self._find_images_by_prompt_matches(prompt)
        
        if not matches or len(matches) <= image_index:
             raise Exception(f"Image not found for prompt '{prompt}' at index {image_index}")

        target_img_data = matches[image_index]
        target_img_element = target_img_data["element"]

        # Ensure visible
        await target_img_element.scroll_into_view_if_needed()

        # Locate the Download button associated with this image.
        # Assumes the button is a sibling or in the same container.
        # We try to find the closest common container.
        # Strategy: Go to parent, checks for button with text "Download".
        
        # User provided snippet: <button ...>...Download...</button>
        # We will look for a button with text "Download" near the image.
        
        # Method 1: Get parent chain and find button
        # This is a heuristic.
        download_btn = target_img_element.locator("xpath=..").locator("button").filter(has_text="Download").first
        
        # Verify if it exists, if not, try one level higher
        if await download_btn.count() == 0:
             download_btn = target_img_element.locator("xpath=../..").locator("button").filter(has_text="Download").first
             
        if await download_btn.count() == 0:
             # Look for the button globally but scoped to the area? Hard without container class.
             # Let's assume the previous logic found it.
             raise Exception("Could not find Download button for the image.")

        await download_btn.click()
        logger.info("Clicked Download button, waiting for menu...")
        
        # Wait for menu options
        # "Download 1K", "Download 2K", "Download 4K"
        # They usually appear in a popover or dropdown. We can search globally for them once menu is open.
        
        option_text = f"Download {scale_option}" # e.g. "Download 2K"
        
        option_btn = self.page.get_by_text(option_text, exact=False)
        
        try:
            await option_btn.wait_for(state="visible", timeout=3000)
        except:
             # Maybe strict match issue?
             logger.warning(f"Option '{option_text}' not found, dumping page for debug...")
             # await self.page.screenshot(path="debug_menu_missing.png")
             raise Exception(f"Upscale option '{option_text}' not found in menu.")

        # Click and start download with error checking
        # First check for any existing errors
        has_error, error_msg = await self._check_for_toast_error()
        if has_error:
            logger.error(f"Website error before upscale: {error_msg}")
            raise WebsiteError(error_msg)
        
        try:
            async with self.page.expect_download(timeout=120000) as download_info:
                await option_btn.click()
                logger.info(f"Clicked {option_text}, waiting for download...")
            
            download = await download_info.value
            
        except Exception as e:
            # Check for error toast if download failed
            has_error, error_msg = await self._check_for_toast_error()
            if has_error:
                logger.error(f"Website error during upscale: {error_msg}")
                raise WebsiteError(error_msg)
            raise
        
        path = await download.path()
        logger.info(f"Download complete: {path}")
        
        # Read file to bytes
        with open(path, "rb") as f:
            file_data = f.read()
        
        # Cleanup temp file
        try:
            import os
            os.remove(path)
            logger.info(f"Deleted temp file: {path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file {path}: {e}")
            
        return io.BytesIO(file_data)


if __name__ == "__main__":
    # Quick test if run directly
    async def main():
        client = NanoBananaClient()
        await client.start()
        print("Browser running. Close the window to stop or wait...")
        # Keep open for a bit
        try:
            await asyncio.sleep(300) # 5 minutes for user to login manually if needed
        except KeyboardInterrupt:
            pass
        finally:
            await client.stop()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
