import os
from dotenv import load_dotenv

load_dotenv()

def parse_peers(peer_str):
    peers = []
    for i in peer_str.split(","):
        node_id, addr = i.split("@")
        host, port = addr.split(":")
        peers.append({"id": node_id, "host": host, "port": int(port)})
    return peers


class Config:
    NODE_ID = os.getenv("NODE_ID")
    USERNAME = os.getenv("USERNAME")
    HOST = os.getenv("HOST")
    PORT = int(os.getenv("PORT"))

    PEERS = parse_peers(os.getenv("PEERS"))

    FILE_SERVER_HOST = os.getenv("FILE_SERVER_HOST")
    FILE_SERVER_PORT = int(os.getenv("FILE_SERVER_PORT"))

    LOG_DIR = os.getenv("LOG_DIR", "logs")