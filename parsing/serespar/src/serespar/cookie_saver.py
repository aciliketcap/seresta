from contextlib import contextmanager
from pathlib import Path
from playwright.sync_api import sync_playwright
import json
import logging

logger = logging.getLogger(__name__)

@contextmanager
def save_login_cookies(login_url: str, success_url: str, auth_material_file: str|Path = "cookies.json"):
    """Drive a manual login and save the resulting cookies as `AuthMaterial`.

    TODO: this is what an `ActiveFlow`'s `LoginProcess` would do, minus the
    `AuthCredentials`: the developer types them into the browser by hand.
    """
    with sync_playwright() as p:
        logger.info(f"Launching browser for login and cookie collection.")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(login_url)
        logger.info(f"Opened URL {login_url} in browser.")
        
        yield page
        
        page.wait_for_url(success_url, timeout=0)
        logger.info("Redirected to the expected page after logging in. Saving cookies...")
        with open(auth_material_file, "w") as f:
            f.write(json.dumps(context.cookies()))
            logger.info(f"Auth material (cookies) saved to {auth_material_file}")
