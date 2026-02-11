
'''
notes:
  https://playwright.dev/python/docs/api/class-playwright
  https://www.blog.pythonlibrary.org/2010/05/22/wxpython-and-threads/

'''

import wx
import asyncio
import threading
import os
from playwright.async_api import async_playwright

# Browser viewport width and height. These can be changed by
# specifying in the class constructor
VP_WIDTH = 1024
VP_HEIGHT = 768

MAX_CONCURRENT_REQUESTS = 10

class PlaywrightWorker(threading.Thread):
    def __init__(self, notify_window, cache_dir="cache",
                  viewport_width=VP_WIDTH, viewport_height=VP_HEIGHT):
        super().__init__()
        self.notify_window = notify_window
        self.cache_dir = cache_dir
        self.daemon = True
        self.loop = None
        self.browser = None
        self.context = None
        self.vp_width = viewport_width
        self.vp_height = viewport_height

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

        self.queue_list_backlog = list()
        self.pending = dict()

    def run(self):
        """Sets up the async event loop and stays alive."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Start Playwright and keep it running
        self.loop.run_until_complete(self._setup_playwright())
        self.loop.run_forever()

    async def _setup_playwright(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        # One context for all project screenshots
        # self.context = await self.browser.new_context(viewport={'width': 1024, 'height': 768})
        self.context = await self.browser.new_context(viewport={
            'width': self.vp_width,
            'height': self.vp_height}
            )


    def request_screenshot(self, project_id, url):
        """Called from wxPython thread to submit work to the async thread."""

        # always add first to queue_list_backlog as tuple
        self.queue_list_backlog.append((project_id,url))
        # we haveto throttle this, to stay within MAX_CONCURRENT_REQUESTS
        if (len(self.pending) <= MAX_CONCURRENT_REQUESTS):
            while len(self.queue_list_backlog) and len(self.pending) <= MAX_CONCURRENT_REQUESTS:
                # FIFO-style, pop the oldest which is at position zero
                project_id, url = self.queue_list_backlog.pop(0)
                self.pending.update({project_id: 'pending'})

                # add another screen-capture task
                if self.loop:
                    asyncio.run_coroutine_threadsafe(
                        self._capture_task(project_id, url), self.loop
                    )

    async def _capture_task(self, project_id, url):
        """The actual async rendering logic."""
        save_path = os.path.join(self.cache_dir, f"{project_id}.png")
        
        # Skip if already cached
        if os.path.exists(save_path):
            # Signal back to wxPython
            wx.CallAfter(self.notify_window.on_screenshot_complete, project_id, save_path)
            return


        page = await self.context.new_page()
        try:
            # wait_until="networkidle" is great for OSHWA project sites
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.screenshot(path=save_path)
            
            # Signal back to wxPython
            wx.CallAfter(self.notify_window.on_screenshot_complete, project_id, save_path)
        except Exception as e:
            wx.CallAfter(self.notify_window.on_screenshot_error, project_id, str(e))
        finally:
            await page.close()
