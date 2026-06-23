from serespar import save_login_cookies
import os
from pathlib import Path

secrets_dir = Path(os.environ["SECRETS_DIR"])

with save_login_cookies(
    login_url="https://www.bigmotoringworld.co.uk/",
    success_url="https://www.bigmotoringworld.co.uk/",
    cookie_file=secrets_dir/"carwow_cookies.json") as page:

    pass # they don't do users
