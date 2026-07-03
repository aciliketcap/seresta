#!/usr/bin/env python3

from time import sleep
from serespar import save_login_cookies
import os
from pathlib import Path
import logging

# TODO: use debug during dev and a sensible logging level in prod
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

secrets_dir = Path(os.environ["SECRETS_DIR"])

with save_login_cookies(
    login_url="https://www.carwow.co.uk/",
    success_url="https://www.carwow.co.uk/",
    cookie_file=secrets_dir/"carwow_cookies.json") as page:
        logging.info("You are given 1 minute to login.")
        sleep(60) # allow developer to login with their credentials
        logging.info("Time's up, cookies will be saved now.")
