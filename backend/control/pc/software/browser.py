# ARIS/control/pc/software/browser.py
"""
Browser Automation module for ARIS — Windows 11
Each operation runs Playwright in its own dedicated thread with a persistent
browser process. Uses a single background thread + queue to avoid thread-switching errors.
"""

import os
import threading
import queue
from datetime import datetime
from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "vision", "screenshots")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# ── Single dedicated browser thread ───────────────────────────────────────────
# All Playwright calls are sent to this one thread via a queue.
# This avoids "cannot switch to a different thread" errors entirely.

_task_queue   = queue.Queue()
_browser_thread = None
_thread_started = False

def _browser_worker():
    """
    Single long-lived thread that owns all Playwright state.
    Reads tasks from _task_queue and executes them, returning results via result_queue.
    """
    pw      = None
    browser = None
    context = None
    page    = None

    def get_page():
        nonlocal pw, browser, context, page
        if pw is None:
            pw = sync_playwright().start()
        if browser is None or not browser.is_connected():
            browser = pw.chromium.launch(
                headless=False,
                args=["--start-maximized", "--no-sandbox"]
            )
        if context is None:
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
        if page is None or page.is_closed():
            page = context.new_page()
        return page

    def do_screenshot(tag="browser"):
        p = get_page()
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{tag}_{ts}.png"
        path     = os.path.join(SCREENSHOT_DIR, filename)
        p.screenshot(path=path, full_page=False)
        return filename

    while True:
        task = _task_queue.get()
        if task is None:
            # Shutdown signal
            try:
                if page and not page.is_closed(): page.close()
                if context: context.close()
                if browser: browser.close()
                if pw:      pw.stop()
            except Exception:
                pass
            break

        fn, result_q = task
        try:
            result = fn(get_page, do_screenshot)
            result_q.put(("ok", result))
        except Exception as e:
            result_q.put(("error", str(e)))


def _ensure_thread():
    """Start the browser worker thread if not already running."""
    global _browser_thread, _thread_started
    if not _thread_started or not _browser_thread.is_alive():
        _browser_thread = threading.Thread(target=_browser_worker, daemon=True)
        _browser_thread.start()
        _thread_started = True


def _run(fn, timeout=60):
    """
    Submit a function to the browser thread and wait for the result.
    fn signature: fn(get_page, do_screenshot) -> dict
    """
    _ensure_thread()
    result_q = queue.Queue()
    _task_queue.put((fn, result_q))
    kind, value = result_q.get(timeout=timeout)
    if kind == "error":
        raise Exception(value)
    return value


# ── Open URL ──────────────────────────────────────────────────────────────────

def open_url(url: str, wait_for: str = "load") -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    def _do(get_page, screenshot):
        page = get_page()
        page.goto(url, wait_until=wait_for, timeout=30000)
        return {
            "action"    : "open_url",
            "url"       : page.url,
            "title"     : page.title(),
            "screenshot": screenshot("page"),
            "status"    : "ok"
        }

    try:
        return _run(_do)
    except Exception as e:
        return {"action": "open_url", "url": url, "status": "error", "error": str(e)}


# ── Google Search ─────────────────────────────────────────────────────────────

def search_google(query: str, max_results: int = 5) -> dict:
    def _do(get_page, screenshot):
        page = get_page()
        page.goto(
            f"https://www.google.com/search?q={query.replace(' ', '+')}",
            wait_until="domcontentloaded",
            timeout=30000
        )
        page.wait_for_selector("div#search", timeout=10000)

        results = []
        for card in page.query_selector_all("div.g"):
            try:
                title_el   = card.query_selector("h3")
                link_el    = card.query_selector("a")
                snippet_el = card.query_selector("div.VwiC3b, span.aCOpRe, div[data-sncf]")

                title   = title_el.inner_text().strip()        if title_el   else ""
                link    = link_el.get_attribute("href")        if link_el    else ""
                snippet = snippet_el.inner_text().strip()[:200] if snippet_el else ""

                if title and link and link.startswith("http"):
                    results.append({"title": title, "url": link, "snippet": snippet})
                    if len(results) >= max_results:
                        break
            except Exception:
                continue

        return {
            "action"    : "search_google",
            "query"     : query,
            "count"     : len(results),
            "results"   : results,
            "screenshot": screenshot("search"),
            "status"    : "ok"
        }

    try:
        return _run(_do)
    except Exception as e:
        return {"action": "search_google", "query": query, "status": "error", "error": str(e)}


# ── Click element ─────────────────────────────────────────────────────────────

def click_element(selector: str = None, text: str = None, x: int = None, y: int = None) -> dict:
    def _do(get_page, screenshot):
        page = get_page()
        if selector:
            page.click(selector, timeout=10000)
            clicked = f"selector: {selector}"
        elif text:
            page.get_by_text(text, exact=False).first.click(timeout=10000)
            clicked = f"text: {text}"
        elif x is not None and y is not None:
            page.mouse.click(x, y)
            clicked = f"coords: ({x},{y})"
        else:
            raise Exception("Provide selector, text, or x/y coordinates")

        page.wait_for_load_state("domcontentloaded")
        return {
            "action"    : "click_element",
            "clicked"   : clicked,
            "url"       : page.url,
            "screenshot": screenshot("click"),
            "status"    : "ok"
        }

    try:
        return _run(_do)
    except Exception as e:
        return {"action": "click_element", "status": "error", "error": str(e)}


# ── Fill form field ───────────────────────────────────────────────────────────

def fill_field(selector: str, value: str, press_enter: bool = False) -> dict:
    def _do(get_page, screenshot):
        page = get_page()
        page.fill(selector, value, timeout=10000)
        if press_enter:
            page.press(selector, "Enter")
            page.wait_for_load_state("domcontentloaded")
        return {
            "action"    : "fill_field",
            "selector"  : selector,
            "value"     : value,
            "submitted" : press_enter,
            "screenshot": screenshot("fill"),
            "status"    : "ok"
        }

    try:
        return _run(_do)
    except Exception as e:
        return {"action": "fill_field", "status": "error", "error": str(e)}


# ── Extract page text ─────────────────────────────────────────────────────────

def get_page_text(max_chars: int = 3000) -> dict:
    def _do(get_page, screenshot):
        page  = get_page()
        text  = page.evaluate("""() => {
            const els = document.querySelectorAll('p,h1,h2,h3,h4,li,span,div');
            let out = '';
            for (const el of els) {
                const t = el.innerText?.trim();
                if (t && t.length > 2) out += t + ' ';
            }
            return out;
        }""")
        text = " ".join(text.split())
        return {
            "action"     : "get_page_text",
            "url"        : page.url,
            "title"      : page.title(),
            "text"       : text[:max_chars],
            "truncated"  : len(text) > max_chars,
            "total_chars": len(text),
            "status"     : "ok"
        }

    try:
        return _run(_do)
    except Exception as e:
        return {"action": "get_page_text", "status": "error", "error": str(e)}


# ── Browser screenshot ────────────────────────────────────────────────────────

def browser_screenshot() -> dict:
    def _do(get_page, screenshot):
        page     = get_page()
        filename = screenshot("manual")
        return {
            "action"    : "browser_screenshot",
            "url"       : page.url,
            "title"     : page.title(),
            "screenshot": filename,
            "url_path"  : f"/vision/image/{filename}",
            "status"    : "ok"
        }

    try:
        return _run(_do)
    except Exception as e:
        return {"action": "browser_screenshot", "status": "error", "error": str(e)}


# ── Get page info ─────────────────────────────────────────────────────────────

def get_page_info() -> dict:
    def _do(get_page, screenshot):
        page = get_page()
        return {
            "action": "get_page_info",
            "url"   : page.url,
            "title" : page.title(),
            "status": "ok"
        }

    try:
        return _run(_do)
    except Exception as e:
        return {"action": "get_page_info", "status": "error", "error": str(e)}


# ── Close browser ─────────────────────────────────────────────────────────────

def close_browser() -> dict:
    try:
        _task_queue.put(None)  # shutdown signal to worker thread
        return {"action": "close_browser", "status": "ok"}
    except Exception as e:
        return {"action": "close_browser", "status": "error", "error": str(e)}
