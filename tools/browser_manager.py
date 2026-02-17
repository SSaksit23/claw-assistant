"""
Singleton Browser Manager for Playwright.

Manages a single browser instance shared across all agents to avoid
re-authentication overhead. Supports headless/headed mode, screenshots,
and cookie/session persistence.
"""

import os
import logging
import asyncio
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Singleton that manages the Playwright browser lifecycle.

    Usage:
        manager = BrowserManager.get_instance()
        page = await manager.get_page()
        # ... do work ...
        await manager.close()
    """

    _instance: Optional["BrowserManager"] = None
    _lock = asyncio.Lock() if hasattr(asyncio, "Lock") else None

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

    @classmethod
    def get_instance(cls) -> "BrowserManager":
        """Return the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _ensure_browser(self):
        """Start Playwright and browser if not already running."""
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
        logger.info(f"Browser started (headless={Config.HEADLESS_MODE})")

    async def get_page(self):
        """Return the shared page instance, starting browser if needed."""
        await self._ensure_browser()
        return self._page

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    @is_logged_in.setter
    def is_logged_in(self, value: bool):
        self._logged_in = value

    async def screenshot(self, name: str = "screenshot") -> str:
        """Take a screenshot for debugging. Returns the file path."""
        os.makedirs("logs", exist_ok=True)
        path = f"logs/{name}.png"
        if self._page:
            await self._page.screenshot(path=path, full_page=True)
            logger.debug(f"Screenshot saved: {path}")
        return path

    async def close(self):
        """Gracefully close browser and Playwright."""
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
            logger.warning(f"Error closing browser: {e}")
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._logged_in = False
            BrowserManager._instance = None
            logger.info("Browser closed")

    async def reset(self):
        """Close and re-create browser (useful after errors)."""
        await self.close()
        await self._ensure_browser()


def run_async(coro):
    """
    Helper to run async code from synchronous context.
    Creates or reuses an event loop.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
