import logging
import os

from .settings import LOG_FILE


NOTIONPY_LOG_LEVEL = os.environ.get("NOTIONPY_LOG_LEVEL", "warning").lower()

logger = logging.getLogger("notion")


def enable_debugging():
    set_log_level(logging.DEBUG)


def set_log_level(level):
    logger.setLevel(level)
    handler.setLevel(level)


if NOTIONPY_LOG_LEVEL == "disabled":
    handler = logging.NullHandler()
    logger.addHandler(handler)
else:
    handler = logging.FileHandler(LOG_FILE)
    formatter = logging.Formatter("\n%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if NOTIONPY_LOG_LEVEL == "debug":
        set_log_level(logging.DEBUG)
    elif NOTIONPY_LOG_LEVEL == "info":
        set_log_level(logging.INFO)
    elif NOTIONPY_LOG_LEVEL == "warning":
        set_log_level(logging.WARNING)
    elif NOTIONPY_LOG_LEVEL == "error":
        set_log_level(logging.ERROR)
    else:
        raise Exception(
            "Invalid value for environment variable NOTIONPY_LOG_LEVEL: {}".format(
                NOTIONPY_LOG_LEVEL
            )
        )
