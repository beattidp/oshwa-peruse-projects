import asyncio
import threading
import os
import wx
from io import BytesIO
from PIL import Image
from playwright.async_api import async_playwright

CACHE_DIR = "cache"
MAX_CONCURRENT_SCREENSHOTS = 6

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
        
        if not force_refresh and os.path.exists(cache_path):
            wx.CallAfter(callback, uid, cache_path)
            return

        async with self.semaphore:
            # Re-check cache inside semaphore if not forcing
            if not force_refresh and os.path.exists(cache_path):
                wx.CallAfter(callback, uid, cache_path)
                return

            context = None
            try:
                context = await browser.new_context(viewport={'width': 1024, 'height': 768})
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                img_bytes = await page.screenshot()
                
                def resize_and_save():
                    img = Image.open(BytesIO(img_bytes))
                    scaled_img = img.resize((512, 384), Image.Resampling.LANCZOS)
                    scaled_img.save(cache_path, format="PNG")

                await asyncio.to_thread(resize_and_save)

                wx.CallAfter(callback, uid, cache_path)

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
