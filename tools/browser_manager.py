"""
Per-Session Browser Manager for Playwright.

Manages a pool of browser instances keyed by session ID, so each
logged-in user gets their own isolated Chromium instance and login state.

Features:
- Per-session browser lifecycle (create / reuse / destroy)
- Idle timeout auto-cleanup (default 30 min)
- Max concurrent browser limit (default 10) to prevent OOM
- LRU eviction when the pool is full

IMPORTANT: Playwright uses asyncio internally. Eventlet monkey-patches
the standard library (socket, select, threading) in ways that break
asyncio.  Therefore all Playwright work MUST run in a REAL OS thread
with an unpatched asyncio event loop.
"""

import os
import time
import asyncio
import logging
import threading
import queue as _queue
from typing import Optional

from config import Config

try:
    from eventlet.patcher import original as _original
    _real_threading = _original("threading")
except Exception:
    _real_threading = threading

logger = logging.getLogger(__name__)

_pool_lock = threading.Lock()


class BrowserManager:
    """
    Per-session browser manager.  Each user session gets its own instance.

    Usage:
        manager = BrowserManager.get_instance(session_id)
        page = await manager.get_page()
    """

    _instances: dict[str, "BrowserManager"] = {}
    _last_access: dict[str, float] = {}
    _active_jobs: dict[str, int] = {}

    MAX_INSTANCES = int(os.getenv("MAX_BROWSER_INSTANCES", "10"))
    IDLE_TIMEOUT = int(os.getenv("BROWSER_IDLE_TIMEOUT", "1800"))  # 30 min

    def __init__(self, session_id: str):
        self._session_id = session_id
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._logged_in = False

    # ------------------------------------------------------------------
    # Pool management
    # ------------------------------------------------------------------
    @classmethod
    def get_instance(cls, session_id: str = "default") -> "BrowserManager":
        to_close: list["BrowserManager"] = []

        with _pool_lock:
            now = time.time()

            expired = [
                sid for sid, ts in cls._last_access.items()
                if now - ts > cls.IDLE_TIMEOUT
            ]
            for sid in expired:
                inst = cls._instances.pop(sid, None)
                cls._last_access.pop(sid, None)
                if inst:
                    to_close.append(inst)
                    logger.info("Evicting idle browser: session=%s", sid)

            if session_id not in cls._instances:
                if len(cls._instances) >= cls.MAX_INSTANCES:
                    oldest_sid = min(cls._last_access, key=cls._last_access.get)
                    inst = cls._instances.pop(oldest_sid, None)
                    cls._last_access.pop(oldest_sid, None)
                    if inst:
                        to_close.append(inst)
                        logger.info("Evicting LRU browser: session=%s", oldest_sid)
                cls._instances[session_id] = cls(session_id)

            cls._last_access[session_id] = now
            result = cls._instances[session_id]

        for inst in to_close:
            _close_sync(inst)

        return result

    @classmethod
    def acquire(cls, session_id: str):
        """Increment the job reference count so the browser isn't destroyed mid-job."""
        with _pool_lock:
            cls._active_jobs[session_id] = cls._active_jobs.get(session_id, 0) + 1
            logger.info("Browser acquired for session=%s (jobs=%d)", session_id, cls._active_jobs[session_id])

    @classmethod
    def release(cls, session_id: str):
        """Decrement the job reference count."""
        with _pool_lock:
            count = cls._active_jobs.get(session_id, 0)
            if count > 1:
                cls._active_jobs[session_id] = count - 1
            else:
                cls._active_jobs.pop(session_id, None)
            logger.info("Browser released for session=%s (jobs=%d)", session_id, max(0, count - 1))

    @classmethod
    def destroy_instance(cls, session_id: str):
        """Remove and close a specific session's browser (async context).
        Skips destruction if other jobs are still using this session."""
        with _pool_lock:
            if cls._active_jobs.get(session_id, 0) > 0:
                logger.info(
                    "Skipping browser destroy for session=%s — %d job(s) still active",
                    session_id, cls._active_jobs[session_id],
                )
                return _noop_coro()
            inst = cls._instances.pop(session_id, None)
            cls._last_access.pop(session_id, None)
        if inst:
            logger.info("Destroying browser for session=%s", session_id)
            return inst.close()
        return _noop_coro()

    @classmethod
    def schedule_destroy(cls, session_id: str):
        """Remove and close a session's browser from a sync/eventlet context.
        Skips destruction if other jobs are still using this session."""
        with _pool_lock:
            if cls._active_jobs.get(session_id, 0) > 0:
                logger.info(
                    "Skipping scheduled browser destroy for session=%s — %d job(s) still active",
                    session_id, cls._active_jobs[session_id],
                )
                return
            inst = cls._instances.pop(session_id, None)
            cls._last_access.pop(session_id, None)
        if inst:
            logger.info("Scheduling browser destroy for session=%s", session_id)
            _close_sync(inst)

    @classmethod
    def active_count(cls) -> int:
        with _pool_lock:
            return len(cls._instances)

    # ------------------------------------------------------------------
    # Browser lifecycle (per instance)
    # ------------------------------------------------------------------
    async def _ensure_browser(self):
        if self._browser and self._browser.is_connected():
            return

        from playwright.async_api import async_playwright

        logger.info("Starting browser for session=%s", self._session_id)
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
        logger.info(
            "Browser started for session=%s (headless=%s, pool=%d/%d)",
            self._session_id, Config.HEADLESS_MODE,
            len(self._instances), self.MAX_INSTANCES,
        )

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
        path = f"logs/{name}_{self._session_id}.png"
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
            logger.warning("Error closing browser for session=%s: %s", self._session_id, e)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            self._logged_in = False
            logger.info("Browser closed for session=%s", self._session_id)

    async def reset(self):
        await self.close()
        await self._ensure_browser()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
async def _noop_coro():
    pass


def _close_sync(instance: BrowserManager):
    """Close a BrowserManager from a synchronous context using a real OS thread."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(instance.close())
        loop.close()
    except Exception as e:
        logger.warning("Error in sync close for session=%s: %s", instance._session_id, e)


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

    import eventlet
    while t.is_alive():
        eventlet.sleep(0.2)

    status, value = result_q.get_nowait()
    if status == "error":
        raise value
    return value


# Backward-compatible alias
run_async = run_in_thread
