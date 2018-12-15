import os
from pathlib import Path

BASE_URL = "https://www.notion.so/"
API_BASE_URL = BASE_URL + "api/v3/"
SIGNED_URL_PREFIX = "https://www.notion.so/signed/"
S3_URL_PREFIX = "https://s3-us-west-2.amazonaws.com/secure.notion-static.com/"
CACHE_DIR = str(Path.home().joinpath(".notion-py-cache"))

try:
	os.makedirs(CACHE_DIR)
except FileExistsError:
	pass