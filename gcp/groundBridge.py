# ===== groundBridge.py =====
import socket
import threading
import json
import queue

class UDPBridge(threading.Thread):
    """
    统一的 UDP 收发桥：
    - 在单一长生命周期 socket 上，同时 bind(接收) 与 sendto(发送)
    - 后台线程循环接收，将解析后的消息投入 out_queue 供 GUI 消费
    - GUI 通过 .send(obj) 即可发送指令
    """
    def __init__(self, bind_addr, send_addrs, out_queue: queue.Queue):
        super().__init__(daemon=True)
        self.bind_addr = bind_addr
        self.send_addrs = send_addrs
        self.out_q: queue.Queue = out_queue
        self._stop = threading.Event()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(self.bind_addr)
        self.sock.settimeout(0.2)

    def run(self):
        while not self._stop.is_set():
            try:
                data, _ = self.sock.recvfrom(65536)
            except socket.timeout:
                continue
            except Exception:
                break

            try:
                msg = json.loads(data.decode("utf-8", "ignore"))
            except Exception:
                continue

            # 批量遥测拆包
            if isinstance(msg, dict) and msg.get("type") == "telemetry_batch" and isinstance(msg.get("list"), list):
                for item in msg["list"]:
                    if isinstance(item, dict):
                        self.out_q.put(item)
            else:
                self.out_q.put(msg)

        # 退出时关闭 socket
        try:
            self.sock.close()
        except Exception:
            pass

    def send(self, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            tmp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for addr in self.send_addrs:
                tmp.sendto(data, addr)
        finally:
            try:
                tmp.close()
            except Exception:
                pass

    def stop(self):
        self._stop.set()
        try:
            self.sock.close()
        except Exception:
            pass