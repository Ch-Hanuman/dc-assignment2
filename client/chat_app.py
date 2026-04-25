import argparse
import http.client
import json
import logging
import os
import sys
import time
from datetime import datetime
from config import Config
from dme import LamportDME
from logger import get_logger

logger = get_logger("chatapp")

class ChatApp:
    def __init__(self):
        self.dme = LamportDME(node_id=Config.DME_NODE_ID, listen_port=Config.PORT, peers=Config.PEERS, log_dir=Config.LOG_DIR)
        logger.info(f"ChatApp started | node={Config.DME_NODE_ID} user={Config.DME_USERNAME} server={Config.HOST}:{Config.PORT}")

    def cmd_view(self):
        logger.info("CMD: view")
        try:
            conn = http.client.HTTPConnection(Config.FILE_SERVER_HOST, Config.FILE_SERVER_PORT, timeout=10)
            conn.request("GET", "/view")
            resp = conn.getresponse()
            body = json.loads(resp.read().decode())
            conn.close()

            if resp.status == 200:
                content = body.get("content", "").rstrip()
                if content:
                    print(content)
                else:
                    print("(chat room is empty)")
                logger.info("View successful")
            else:
                print(f"[ERROR] Server returned {resp.status}: {body}")
                logger.error(f"View failed: {resp.status} {body}")

        except Exception as e:
            print(f"[ERROR] Could not reach file server: {e}")
            logger.error(f"View exception: {e}")

    def cmd_post(self, text):
        timestamp = datetime.now().strftime("%d %b %H:%M")
        message   = f"{timestamp} {Config.DME_USERNAME}: {text}"

        logger.info(f"CMD: post | message='{message}'")
        logger.info("Requesting DME lock before write...")

        t_acquire_start = time.time()
        self.dme.acquire()
        t_acquire_end   = time.time()
        logger.info(f"DME lock granted after {t_acquire_end - t_acquire_start:.3f}s")

        success = False
        try:
            payload = json.dumps({"message": message}).encode()
            conn    = http.client.HTTPConnection(Config.FILE_SERVER_HOST, Config.FILE_SERVER_PORT, timeout=10)
            conn.request("POST", "/post", body=payload,
                headers={"Content-Type": "application/json", "Content-Length": str(len(payload))}
            )
            resp    = conn.getresponse()
            resp_body  = json.loads(resp.read().decode())
            conn.close()

            if resp.status == 200:
                logger.info(f"Post successful | message='{message}'")
                success = True
            else:
                logger.error(f"Post failed: {resp.status} {resp_body}")
                print(f"[ERROR] Server error: {resp_body}")

        except Exception as e:
            logger.error(f"Post exception: {e}")
            print(f"[ERROR] Could not reach file server: {e}")

        finally:
            self.dme.release()
            logger.info("DME lock released")

        if success:
            print("Message Sent")

    def run_repl(self):
        prompt = f"{Config.DME_USERNAME}@{Config.DME_NODE_ID}> "
        print(f"\n=== Chat Room  |  node={Config.DME_NODE_ID}  user={Config.DME_USERNAME} ===")
        print("Commands:  view  |  post <text>  |  quit\n")

        while True:
            try:
                raw = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("Tata Tata Bye Bye")
                break

            if not raw:
                continue

            if raw in ("quit", "exit", "q"):
                print("Tata Tata Bye Bye")
                break

            if raw == "view":
                self.cmd_view()

            elif raw.startswith("post ") or raw.startswith("post\""):
                text = raw[5:].strip().strip('"').strip("'")
                if text:
                    self.cmd_post(text)
                else:
                    print("Usage: post <text>")

            elif raw == "post":
                print("Usage: post <text>")

            else:
                print(f"Unknown command: '{raw}'  (try: view | post <text> | quit)")


def main():
    app = ChatApp()
    app.run_repl()


if __name__ == "__main__":
    main()
