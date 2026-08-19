#!/usr/bin/env python3

from time import sleep
from serespar import save_login_cookies
import logging

from .config import CarWowParserConfig

# TODO: use debug during dev and a sensible logging level in prod
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# Only the parser layer: this runs before there is a task, and the login URLs
# and the time the developer gets are carwow's own defaults.
config = CarWowParserConfig()

with save_login_cookies(
    login_url=config.login_url,
    success_url=config.login_success_url,
    auth_material_file=config.auth_material_path
    ) as page:
        logging.info("You are given %s seconds to login.", config.manual_login_seconds)
        sleep(config.manual_login_seconds) # allow developer to login with their credentials
        logging.info("Time's up, cookies will be saved now.")
