import os
import logging
from config import Config

LOG_FILE  = os.path.join(os.path.dirname(__file__), Config.LOG_DIR, "client.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.FileHandler(LOG_FILE)
        formatter = logging.Formatter(
            f"%(asctime)s.%(msecs)03d [CHATAPP-{Config.DME_NODE_ID}] %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    return logger