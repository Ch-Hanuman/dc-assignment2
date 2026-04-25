import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    HOST = os.getenv("HOST")
    PORT = int(os.getenv("PORT"))
    LOG_DIR = os.getenv("LOG_DIR")