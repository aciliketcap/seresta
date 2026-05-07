from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright
import json
import logging

logger = logging.getLogger(__name__)

@contextmanager
def save_login_cookies(login_url: str, success_url: str, cookie_file: str|Path = "cookies.json"):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url)
        
        yield page
        
        page.wait_for_url(success_url, timeout=0)
        logger.info("Redirected to the expected page after logging in. Saving cookies")
        with open(cookie_file, "w") as f:
            f.write(json.dumps(context.cookies()))
            logger.info(f"Cookies saved to {cookie_file}")
