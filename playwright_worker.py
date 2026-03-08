import asyncio
import threading
import os
import wx
from io import BytesIO
from PIL import Image
from playwright.async_api import async_playwright

CACHE_DIR = "cache"
MAX_CONCURRENT_SCREENSHOTS = 6

# Screenshot and Thumbnail Constants
SCREENSHOT_WIDTH = 1024
SCREENSHOT_HEIGHT = 768
DEPTH_MULTIPLIER = 1.5

THUMB_WIDTH = 256
THUMB_HEIGHT = 192
THUMB_CROP_PERCENT = 0.15

class ScreenshotWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = None
        self.queue = None
        self.semaphore = None

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.main_loop())

    async def main_loop(self):
        self.queue = asyncio.PriorityQueue()
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCREENSHOTS)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            while True:
                # PriorityQueue returns (priority, data)
                item = await self.queue.get()
                if item is None:
                    break
                
                priority, uid, url, callback, force_refresh = item
                asyncio.create_task(self.process_request(browser, uid, url, callback, force_refresh))

            await browser.close()

    async def process_request(self, browser, uid, url, callback, force_refresh):
        cache_path = os.path.join(CACHE_DIR, f"{uid}.png")
        thumb_path = os.path.join(CACHE_DIR, f"{uid}_thumb.png")
        
        if not force_refresh and os.path.exists(thumb_path):
            wx.CallAfter(callback, uid, thumb_path)
            return

        async with self.semaphore:
            # Re-check cache inside semaphore if not forcing
            if not force_refresh and os.path.exists(thumb_path):
                wx.CallAfter(callback, uid, thumb_path)
                return

            context = None
            try:
                context = await browser.new_context(viewport={'width': SCREENSHOT_WIDTH, 'height': int(SCREENSHOT_HEIGHT * DEPTH_MULTIPLIER)})
                page = await context.new_page()
                await page.goto(url, wait_until="load", timeout=30000)
                img_bytes = await page.screenshot()
                
                def process_images():
                    # Save Master
                    img = Image.open(BytesIO(img_bytes))
                    
                    is_github = url.startswith("https://github.com/")
                    if is_github:
                        # Crop 50px top, 312px right, 301px bottom
                        right = SCREENSHOT_WIDTH - 312
                        bottom = int(SCREENSHOT_HEIGHT * DEPTH_MULTIPLIER) - 301
                        img = img.crop((0, 50, right, bottom))
                        
                    img.save(cache_path, format="PNG")

                    # Create Thumbnail
                    if is_github:
                        # Crop top 534px (2/3 of the 801px cropped master)
                        crop_box = (0, 0, right, 534)
                        cropped_img = img.crop(crop_box)
                    else:
                        # 1. Crop top portion (original SCREENSHOT_HEIGHT)
                        crop_box = (0, 0, SCREENSHOT_WIDTH, SCREENSHOT_HEIGHT)
                        cropped_img = img.crop(crop_box)
                    
                    # 2. Scale width to THUMB_WIDTH, preserving aspect ratio
                    w, h = cropped_img.size
                    scale = THUMB_WIDTH / float(w)
                    new_h = int(h * scale)
                    thumb = cropped_img.resize((THUMB_WIDTH, new_h), Image.Resampling.LANCZOS)
                    
                    # 3. Center crop to target thumbnail height
                    main_crop_h = int(THUMB_HEIGHT * THUMB_CROP_PERCENT)
                    target_final_h = THUMB_HEIGHT - 2 * main_crop_h
                    
                    crop_top = (thumb.height - target_final_h) // 2
                    thumb_crop_box = (0, crop_top, THUMB_WIDTH, crop_top + target_final_h)
                    final_thumb = thumb.crop(thumb_crop_box)
                    
                    final_thumb.save(thumb_path, format="PNG")

                await asyncio.to_thread(process_images)

                wx.CallAfter(callback, uid, thumb_path)

            except Exception as e:
                print(f"Error fetching {url} for {uid}: {e}")
            finally:
                if context:
                    await context.close()

    def request_screenshot(self, uid, url, callback, priority=10, force_refresh=False):
        if not self.loop or not self.queue:
            return
            
        def _enqueue():
            # (priority, uid, url, callback, force_refresh)
            # Standard background fetches use priority 10
            # Selection-based fetches use priority 5
            # Manual reloads use priority 0
            self.queue.put_nowait((priority, uid, url, callback, force_refresh))
            
        self.loop.call_soon_threadsafe(_enqueue)
