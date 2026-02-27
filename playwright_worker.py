import asyncio
import threading
import os
import wx
from io import BytesIO
from PIL import Image
from playwright.async_api import async_playwright

CACHE_DIR = "cache"

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
        self.queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(6)
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            
            while True:
                req = await self.queue.get()
                if req is None:
                    break
                
                uid, url, callback = req
                asyncio.create_task(self.process_request(browser, uid, url, callback))

            await browser.close()

    async def process_request(self, browser, uid, url, callback):
        cache_path = os.path.join(CACHE_DIR, f"{uid}.png")
        
        if os.path.exists(cache_path):
            wx.CallAfter(callback, uid, cache_path)
            return

        async with self.semaphore:
            if os.path.exists(cache_path):
                wx.CallAfter(callback, uid, cache_path)
                return

            context = None
            try:
                context = await browser.new_context(viewport={'width': 1024, 'height': 768})
                page = await context.new_page()
                
                await page.goto(url, wait_until="networkidle", timeout=30000)
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

    def request_screenshot(self, uid, url, callback):
        if not self.loop or not self.queue:
            return
            
        def _enqueue():
            self.queue.put_nowait((uid, url, callback))
            
        self.loop.call_soon_threadsafe(_enqueue)
