import json
import logging
import os
import socket
import threading
import time
from datetime import datetime

def make_logger(node_id, log_dir):
    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(f"DME-{node_id}")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s | %(message)s", datefmt="%d %b %H:%M:%S")
    fh = logging.FileHandler(os.path.join(log_dir, f"dme_{node_id}.log"))
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


MSG_REQUEST = "REQUEST"
MSG_REPLY   = "REPLY"
MSG_RELEASE = "RELEASE"


class LamportDME:
    def __init__(self, node_id, listen_port, peers, log_dir):
        self.node_id      = node_id
        self.listen_port  = listen_port
        self.peers        = peers
        self.peer_ids     = [p["id"] for p in peers]
        self.n_peers      = len(peers)
        self.log          = make_logger(node_id, log_dir)

        # Lamport logical clock
        self.clock       = 0
        self.clock_lock  = threading.Lock()

        # Request queue: list of (timestamp, node_id)  sorted by (ts, id)
        self.queue       = []
        self.queue_lock  = threading.Lock()

        # Track latest known timestamp from each peer (for queue head check)
        self.peer_ts     = {p["id"]: 0 for p in peers}

        # Replies received since last REQUEST broadcast
        self.replies     = set()
        self.replies_lock = threading.Lock()

        # CS state
        self.in_cs       = False
        self.want_cs     = False
        self.cs_granted  = threading.Event()

        # Start listener thread
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("0.0.0.0", listen_port))
        self.server_sock.listen(16)
        self.listener_thread = threading.Thread(target=self.listener, daemon=True, name=f"dme-listen-{node_id}")
        self.listener_thread.start()
        self.log.info(f"DME listener started on port {listen_port}")
        self.log.info(f"Peers: {self.peer_ids}")

    def acquire(self):
        self.want_cs = True
        self.cs_granted.clear()
        with self.replies_lock:
            self.replies.clear()

        ts = self.tick()
        entry = (ts, self.node_id)

        with self.queue_lock:
            self.queue.append(entry)
            self.queue.sort(key=lambda x: (x[0], x[1]))

        self.log.info(f"ACQUIRE REQUEST | clock={ts} | queue={self.queue}")

        # Broadcast REQUEST to all peers
        self.broadcast(MSG_REQUEST, ts)

        # Wait until conditions are met
        self.log.info("Waiting for CS permission …")
        self.cs_granted.wait()
        self.in_cs = True
        self.log.info(f"*** CRITICAL SECTION ENTERED *** | clock={self.clock}")

    def release(self):
        if not self.in_cs:
            return

        self.in_cs   = False
        self.want_cs = False

        ts = self.tick()

        with self.queue_lock:
            self.queue = [e for e in self.queue if e[1] != self.node_id]

        self.log.info(f"RELEASE | clock={ts} | queue after={self.queue}")

        # Broadcast RELEASE to all peers
        self._broadcast(MSG_RELEASE, ts)
        self.log.info("*** CRITICAL SECTION RELEASED ***")


    def tick(self):
        with self.clock_lock:
            self.clock += 1
            return self.clock
        
    def update_clock(self, recv_ts):
        with self.clock_lock:
            self.clock = max(self.clock, recv_ts) + 1
            return self.clock

    def broadcast(self, msg_type, ts):
        for peer in self.peers:
            self.send_msg(peer, msg_type, ts)

    def send_msg(self, peer, msg_type, ts):
        payload = json.dumps({
            "type":    msg_type,
            "ts":      ts,
            "node_id": self.node_id
        }).encode()

        def try_send():
            retries = 5
            for attempt in range(retries):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(3)
                    s.connect((peer["host"], peer["port"]))
                    s.sendall(payload)
                    s.close()
                    self.log.debug(f"SENT {msg_type} ts={ts} -> {peer['id']}")
                    return
                except Exception as e:
                    if attempt < retries - 1:
                        time.sleep(0.2 * (attempt + 1))
                    else:
                        self.log.error(f"Failed to send {msg_type} to {peer['id']}: {e}")

        t = threading.Thread(target=try_send, daemon=True)
        t.start()

    def check_cs_condition(self):
        if not self.want_cs:
            return

        with self.queue_lock:
            if not self.queue:
                return
            head_ts, head_node = self.queue[0]
            is_head = (head_node == self.node_id)

        with self.replies_lock:
            have_all_replies = (len(self.replies) == self.n_peers)

        if is_head and have_all_replies:
            self.cs_granted.set()

    def listener(self):
        while True:
            try:
                conn, addr = self.server_sock.accept()
                t = threading.Thread(
                    target=self.handle_conn,
                    args=(conn, addr),
                    daemon=True
                )
                t.start()
            except Exception as e:
                self.log.error(f"Listener error: {e}")

    def handle_conn(self, conn, addr):
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
            conn.close()

            msg     = json.loads(data.decode())
            msg_type = msg["type"]
            recv_ts  = msg["ts"]
            sender   = msg["node_id"]

            new_clock = self.update_clock(recv_ts)
            self.peer_ts[sender] = max(self.peer_ts.get(sender, 0), recv_ts)

            self.log.debug( f"RECV {msg_type} ts={recv_ts} from={sender} | local_clock={new_clock}")

            if msg_type == MSG_REQUEST:
                self.handle_request(sender, recv_ts, new_clock)

            elif msg_type == MSG_REPLY:
                self.handle_reply(sender, recv_ts)

            elif msg_type == MSG_RELEASE:
                self.handle_release(sender, recv_ts)

        except Exception as e:
            self.log.error(f"Handle conn error: {e}")

    def handle_request(self, sender, recv_ts, new_clock):
        with self.queue_lock:
            self.queue.append((recv_ts, sender))
            self.queue.sort(key=lambda x: (x[0], x[1]))
            q_snapshot = list(self.queue)

        self.log.info(f"REQUEST from {sender} ts={recv_ts} | queue={q_snapshot}")
        reply_ts = self.tick()
        peer = next(p for p in self.peers if p["id"] == sender)
        self.send_msg(peer, MSG_REPLY, reply_ts)
        self.log.info(f"REPLIED to {sender} with ts={reply_ts}")
        with self.replies_lock:
            self.replies.add(sender)
        self.check_cs_condition()

    def handle_reply(self, sender, recv_ts):
        with self.replies_lock:
            self.replies.add(sender)
            replies_snapshot = set(self.replies)

        self.log.info(f"REPLY from {sender} ts={recv_ts} | replies so far={replies_snapshot}")
        self.check_cs_condition()

    def handle_release(self, sender: str, recv_ts: int):
        with self.queue_lock:
            before = list(self.queue)
            self.queue = [e for e in self.queue if e[1] != sender]
            after  = list(self.queue)

        self.log.info(f"RELEASE from {sender} ts={recv_ts} | queue {before} -> {after}")
        self.check_cs_condition()
