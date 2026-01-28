from serespar import save_login_cookies
from time import sleep
import os
from pathlib import Path

secrets_dir = Path(os.environ["SECRETS_DIR"])

with save_login_cookies(
    login_url="https://www.linkedin.com/",
    success_url="https://www.linkedin.com/feed/*",
    cookie_file=secrets_dir/"linkedin_cookies.json") as page:

    # login manually before time runs out!
    sleep(30)
