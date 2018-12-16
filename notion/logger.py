import logging

from .settings import LOG_FILE


logger = logging.getLogger('notion')

handler = logging.FileHandler(LOG_FILE)
handler.setLevel(logging.WARN)

formatter = logging.Formatter('\n%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logger.addHandler(handler)

def enable_debugging():
	logger.setLevel(logging.DEBUG)
	handler.setLevel(logging.DEBUG)
