import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from config import Config

CHAT_FILE = os.path.join(os.path.dirname(__file__), "chat.txt")
LOG_FILE  = os.path.join(os.path.dirname(__file__), Config.LOG_DIR, "server.log")
os.makedirs(Config.LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SERVER] %(levelname)s | %(message)s",
    datefmt="%d %b %H:%M:%S",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)]
)
logger = logging.getLogger("file_server")
file_lock = asyncio.Lock()


class PostRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        description="Fully-formatted chat line, e.g. '12 Oct 09:01 Lucy: Hello'"
    )

class ViewResponse(BaseModel):
    content: str

class PostResponse(BaseModel):
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.path.exists(CHAT_FILE):
        with open(CHAT_FILE, "w") as f:
            f.write("")
        logger.info(f"Created new chat file at {CHAT_FILE}")
    else:
        logger.info(f"Using existing chat file at {CHAT_FILE}")
    logger.info(f"File server ready on {Config.HOST}:{Config.PORT}")
    yield
    logger.info("File server shutting down.")

app = FastAPI(title="Chat Room File Server", lifespan=lifespan)

@app.get("/view", response_model=ViewResponse)
async def view():
    try:
        with open(CHAT_FILE, "r") as f:
            content = f.read()
        lines = len(content.splitlines())
        logger.info(f"VIEW -> {lines} line(s) returned")
        return ViewResponse(content=content)
    except OSError as e:
        logger.error(f"VIEW failed: {e}")
        raise HTTPException(status_code=500, detail=f"Could not read chat file: {e}")

@app.post("/post", response_model=PostResponse)
async def post(body: PostRequest):
    async with file_lock:
        try:
            with open(CHAT_FILE, "a") as f:
                f.write(body.message + "\n")
            logger.info(f"POST  -> appended: {body.message!r}")
            return PostResponse(message=body.message)
        except OSError as e:
            logger.error(f"POST failed: {e}")
            raise HTTPException(status_code=500, detail=f"Could not write chat file: {e}")


if __name__ == "__main__":
    uvicorn.run("file_server:app", host=Config.HOST, port=Config.PORT, log_level="warning", reload=False)
