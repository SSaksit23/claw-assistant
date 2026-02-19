"""
Singleton Browser Manager for Playwright.

Manages a single browser instance shared across all agents to avoid
re-authentication overhead. Supports headless/headed mode, screenshots,
and cookie/session persistence.

IMPORTANT: Playwright uses asyncio internally. Eventlet monkey-patches
the standard library (socket, select, threading) in ways that break
asyncio.  Therefore all Playwright work MUST run in a REAL OS thread
with an unpatched asyncio event loop.

We obtain the *original* (unpatched) threading module via
eventlet.patcher.original() so that our ThreadPoolExecutor creates
actual OS threads, not eventlet green threads.
"""

import os
import asyncio
import logging
import threading
import queue as _queue
from typing import Optional

from config import Config

# Get the REAL (unpatched) threading module so we can spawn actual OS
# threads even after eventlet.monkey_patch(thread=True).
try:
    from eventlet.patcher import original as _original
    _real_threading = _original("threading")
except Exception:
    _real_threading = threading

logger = logging.getLogger(__name__)

_thread_lock = threading.Lock()


class BrowserManager:
    """
    Singleton that manages the Playwright browser lifecycle.

    Usage (sync, from any greenlet):
        result = run_in_thread(some_async_playwright_function())
    """

    _instance: Optional["BrowserManager"] = None

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

    @classmethod
    def get_instance(cls) -> "BrowserManager":
        with _thread_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def _ensure_browser(self):
        if self._browser and self._browser.is_connected():
            return

        from playwright.async_api import async_playwright

        logger.info("Starting Playwright browser...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=Config.HEADLESS_MODE,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(Config.BROWSER_TIMEOUT)
        logger.info("Browser started (headless=%s)", Config.HEADLESS_MODE)

    async def get_page(self):
        await self._ensure_browser()
        return self._page

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    @is_logged_in.setter
    def is_logged_in(self, value: bool):
        self._logged_in = value

    async def screenshot(self, name: str = "screenshot") -> str:
        os.makedirs("logs", exist_ok=True)
        path = f"logs/{name}.png"
        if self._page:
            await self._page.screenshot(path=path, full_page=True)
            logger.debug("Screenshot saved: %s", path)
        return path

    async def close(self):
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning("Error closing browser: %s", e)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._logged_in = False
            BrowserManager._instance = None
            logger.info("Browser closed")

    async def reset(self):
        await self.close()
        await self._ensure_browser()


def run_in_thread(coro):
    """
    Run an async Playwright coroutine in a REAL OS thread so it gets
    a clean asyncio event loop, free from eventlet monkey-patching.

    Uses the *original* (unpatched) threading.Thread to guarantee a
    native OS thread.  Instead of t.join() (which would block the
    eventlet event loop), we poll t.is_alive() and yield to eventlet
    between checks so heartbeats keep flowing.
    """
    result_q: _queue.Queue = _queue.Queue()

    def _worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(coro)
            result_q.put(("ok", result))
        except Exception as exc:
            result_q.put(("error", exc))
        finally:
            loop.close()

    t = _real_threading.Thread(target=_worker, daemon=True)
    t.start()

    # Poll for thread completion, yielding to eventlet so the
    # WebSocket heartbeat loop is never starved.
    import eventlet
    while t.is_alive():
        eventlet.sleep(0.2)

    status, value = result_q.get_nowait()
    if status == "error":
        raise value
    return value


# Backward-compatible alias
run_async = run_in_thread
