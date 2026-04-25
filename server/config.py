import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    HOST = os.getenv("HOST")
    PORT = int(os.getenv("PORT"))