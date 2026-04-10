
# dronesBridge.py (typed-queue version)
#!/usr/bin/env python3
import socket, json, threading, asyncio, builtins, queue

class FGCBridge:
    def __init__(
        self,
        bind_ip="0.0.0.0",
        bind_port=0,
        gui_host="127.0.0.1",
        gui_port=56999,
        peers=None,
        name="drone",
    ):

        self.gui_addr = (gui_host, gui_port)
        self.bind_ip, self.bind_port = bind_ip, bind_port
        self.name = name

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.bind_ip, self.bind_port))
        self.sock.setblocking(True)

        self._q_cmd = queue.Queue()
        self._q_peer = queue.Queue(maxsize=50)
        self._q_misc = queue.Queue()
        self._stop = threading.Event()
        self._rx_th = None

        self._orig_print = builtins.print
        self._print_patched = False

        self.peers = list(peers or [])

    # --- rx thread ---
    def _rx_loop(self):
        while not self._stop.is_set():
            try:
                data, addr = self.sock.recvfrom(65536)
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8","ignore"))
                if isinstance(msg, dict):
                    msg["_from"] = f"{addr[0]}:{addr[1]}"
                    if "cmd" in msg:
                        self._q_cmd.put(msg)
                    elif msg.get("type") == "lead_broadcast":
                        try:
                            self._q_peer.put_nowait(msg)
                        except queue.Full:
                            pass
                    else:
                        self._q_misc.put(msg)
            except Exception:
                continue

    async def start(self):
        if self._rx_th and self._rx_th.is_alive():
            return
        self._stop.clear()
        self._rx_th = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_th.start()

    async def _await_queue(self, q):
        return await asyncio.to_thread(q.get)

    async def next_cmd(self):
        return await self._await_queue(self._q_cmd)

    async def next_peer(self):
        return await self._await_queue(self._q_peer)

    async def next_misc(self):
        return await self._await_queue(self._q_misc)

    # --- send helpers ---
    def _sendto(self, addr, payload):
        try:
            self.sock.sendto(json.dumps(payload, ensure_ascii=False).encode("utf-8"), addr)
        except Exception:
            pass

    def send_gui(self, payload):
        self._sendto(self.gui_addr, payload)

    def send_telemetry(self, **fields):
        self.send_gui({"type":"telemetry", **fields})

    def send_log(self, text):
        self.send_gui({"type":"log", "text": str(text)})

    def send_to_peer(self, ip, port, payload):
        self._sendto((ip,port), payload)

    def send_to_peers(self, payload):
        for ip,port in self.peers:
            self._sendto((ip,port), payload)

    def patch_print(self):
        if self._print_patched: return
        def _patched_print(*args, **kwargs):
            try:
                self.send_log(" ".join(str(a) for a in args))
            except Exception:
                pass
            return self._orig_print(*args, **kwargs)
        builtins.print = _patched_print
        self._print_patched = True

    def unpatch_print(self):
        if self._print_patched:
            builtins.print = self._orig_print
            self._print_patched = False

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except Exception:
            pass
