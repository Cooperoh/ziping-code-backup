import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from groundBridge import UDPBridge
from pageMonitor import MonitorPage
from pageFormation import FormationAssignmentPage
from pageStarlink import StarlinkPage

APP_TITLE = "Ground Control Panel"
# CMD_ADDR = ("192.168.8.67", 57000)
CMD_ADDRS = [
    ("10.144.1.1", 57000),
    ("10.144.1.2", 57000),
    # ("10.144.1.0", 57000), # 一号机，用wsl临时代替
    # ("10.144.1.0", 57001), # 二号机，用wsl临时代替
    ("10.144.1.3", 57000), # 三号机，用wsl临时代替
]
TELEM_ADDR = ("0.0.0.0", 56999) # default is 56999
# HOME_LAT = 38.0667
# HOME_LON = 118.1575
HOME_LAT = 38.3094
HOME_LON = 117.680
STARLINK_EXEC_CMD = "target_location_starlink_sim"

# # 北京经纬度
# HOME_LAT = 39.9042
# HOME_LON = 116.4074

# netsh int ipv4 show excludedportrange protocol=udp

class GroundControlApp(tk.Tk):
    """Main window: manages shared state, networking, and pages."""

    formation_types = {
        "三角": 1,
        "横向一线": 2,
        "纵向一线": 3,
    }

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x800")

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.state_lock = threading.Lock()
        self.drone_state = {}
        self.tracks = {}
        self.known_drones = set()

        self.group_assignments = {0: [], 1: [], 2: [], 3: []}
        self.group_leaders = {0: None, 1: None, 2: None, 3: None}
        self.active_formations = set()

        self._msg_q = queue.Queue()
        self.bridge = UDPBridge(
            bind_addr=TELEM_ADDR,
            send_addrs=CMD_ADDRS,
            out_queue=self._msg_q,
        )
        self.bridge.start()

        self.home_lat = HOME_LAT
        self.home_lon = HOME_LON

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        self.monitor_page = MonitorPage(self.nb, self)
        self.assignment_page = FormationAssignmentPage(self.nb, self)
        self.starlink_page = StarlinkPage(self.nb, self)

        self.nb.add(self.monitor_page, text="Monitor")
        self.nb.add(self.assignment_page, text="Formation")
        self.nb.add(self.starlink_page, text="Starlink")

        self.monitor_page.map.set_position(self.home_lat, self.home_lon)
        self.monitor_page.map.set_zoom(14)
        self.starlink_page.map.set_position(self.home_lat, self.home_lon)
        self.starlink_page.map.set_zoom(14)

        self.after(50, self._poll_messages)
        self.after(100, self._refresh_pages)

    # --------------------------------------------------------------- ui helpers
    def _append_log(self, text):
        self.monitor_page.append_log(text)
        self.starlink_page.append_log(text)

    # ---------------------------------------------------------------- network
    def _poll_messages(self):
        for _ in range(200):
            try:
                msg = self._msg_q.get_nowait()
            except queue.Empty:
                break
            self._handle_message(msg)
        self.after(50, self._poll_messages)

    def _handle_message(self, msg):
        if isinstance(msg, dict):
            mtype = msg.get("type")
            if mtype == "log":
                text = msg.get("text", "")
                if text:
                    self._append_log(text)
                return
            if mtype == "starlink_sender_report":
                self.starlink_page.handle_starlink_report(msg)
                return
            if mtype == "telemetry":
                drone_id = msg.get("id")
                if drone_id is None:
                    return
                if isinstance(drone_id, str) and drone_id.isdigit():
                    drone_id = int(drone_id)
                if not isinstance(drone_id, int):
                    return
                self._register_drone(drone_id)
                with self.state_lock:
                    state = self.drone_state.setdefault(drone_id, {})
                    for key in ("lat", "lon", "speed", "heading", "err_s", "err_d", "tag"):
                        value = msg.get(key)
                        if value is not None:
                            state[key] = value
                    goto_lat_present = "goto_lat" in msg
                    goto_lon_present = "goto_lon" in msg
                    if goto_lat_present or goto_lon_present:
                        goto_lat = msg.get("goto_lat")
                        goto_lon = msg.get("goto_lon")
                        try:
                            if goto_lat is None or goto_lon is None:
                                raise ValueError
                            state["goto_lat"] = float(goto_lat)
                            state["goto_lon"] = float(goto_lon)
                        except (TypeError, ValueError):
                            state.pop("goto_lat", None)
                            state.pop("goto_lon", None)
                    lat = state.get("lat")
                    lon = state.get("lon")
                    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                        track = self.tracks.setdefault(drone_id, [])
                        if not track or (
                            abs(track[-1][0] - lat) > 1e-6
                            or abs(track[-1][1] - lon) > 1e-6
                        ):
                            track.append((lat, lon))
                return
        if isinstance(msg, str):
            self._append_log(msg)

    # ----------------------------------------------------------------- refresh
    def _refresh_pages(self):
        with self.state_lock:
            state_snapshot = dict(self.drone_state)
            tracks_snapshot = {k: list(v) for k, v in self.tracks.items()}
        show_errors = bool(self.active_formations)
        self.monitor_page.refresh(state_snapshot, tracks_snapshot, show_errors)
        self.starlink_page.refresh(state_snapshot, tracks_snapshot, show_errors)
        self.after(150, self._refresh_pages)

    # -------------------------------------------------------------- drone data
    def _register_drone(self, drone_id):
        if drone_id not in self.known_drones:
            self.known_drones.add(drone_id)
            if drone_id not in self.group_assignments[0]:
                self.group_assignments[0].append(drone_id)
                self.group_assignments[0] = sorted(set(self.group_assignments[0]))
            if self.group_leaders[0] is None:
                self.group_leaders[0] = drone_id
            self.assignment_page.update_drone_roster([drone_id])
            leader_flag = self.group_leaders[0] == drone_id
            self._send_config_update(drone_id, 0, leader_flag)

    def clear_tracks_history(self):
        with self.state_lock:
            self.tracks = {key: [] for key in self.tracks.keys()}

    def clear_goto_targets(self):
        with self.state_lock:
            for state in self.drone_state.values():
                state.pop("goto_lat", None)
                state.pop("goto_lon", None)
        self.monitor_page.clear_goto_overlays()
        self.starlink_page.clear_goto_overlays()

    def get_home_location(self):
        return self.home_lat, self.home_lon

    # --------------------------------------------------------- command helpers

    def _resolve_command_targets(self):
        group_id = self.monitor_page.get_selected_group()
        if group_id is None:
            self._append_log("[提示] 请先选择目标编队。")
            return None

        members = self.group_assignments.get(group_id, [])
        if not members:
            self._append_log(f"[提示] {MonitorPage.GROUP_LABELS[group_id]} 暂无无人机。")
            return None
        return group_id, list(members)

    def handle_basic_command(self, command):
        resolved = self._resolve_command_targets()
        if not resolved:
            return
        group_id, targets = resolved
        payload = {"cmd": command, "targets": targets, "group": group_id}
        self._send_command(payload)

    def handle_formation_command(self):
        resolved = self._resolve_command_targets()
        if not resolved:
            return
        group_id, targets = resolved
        try:
            form_type_name = self.monitor_page.form_type_var.get()
            form_type = int(self.formation_types[form_type_name])
            spacing = float(self.monitor_page.dist_var.get())
        except Exception:
            messagebox.showwarning("参数错误", "请正确选择编队类型并输入数字距离。")
            return
        config_payload = {
            "cmd": "formation_set",
            "group": group_id,
            "targets": targets,
            "form_type": form_type,
            "spacing": spacing,
        }
        start_payload = {
            "cmd": "formation_start",
            "group": group_id,
            "targets": targets,
            "form_type": form_type,
            "spacing": spacing,
        }
        self._send_command(config_payload)
        self._send_command(start_payload)
        self.active_formations.add(group_id)
        self._append_log(
            f"[编队] 已向 {MonitorPage.GROUP_LABELS[group_id]} 下发：类型 {form_type}，间距 {spacing:.1f} 米，成员 {targets}"
        )

    def _send_command(self, payload):
        try:
            self.bridge.send(payload)
        except Exception as exc:
            messagebox.showerror("网络错误", f"发送失败：{exc}")

    def _send_config_update(self, drone_id, group_id, leader):
        payload = {
            "cmd": "config_update",
            "id": drone_id,
            "group": group_id,
            "is_leader": 1 if leader else 0,
        }
        self._send_command(payload)

    def send_starlink_location(self, location):
        try:
            lat, lon = location
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            messagebox.showwarning("参数错误", "请先提供有效的经纬度。")
            return
        payload = {
            "cmd": STARLINK_EXEC_CMD,
            "location": [lat, lon],
        }
        self._send_command(payload)


    def on_assignments_uploaded(self, members, leaders):
        for group_id in range(4):
            group_members = list(sorted(set(members.get(group_id, []))))
            self.group_assignments[group_id] = group_members
            leader_id = leaders.get(group_id)
            if leader_id in group_members:
                self.group_leaders[group_id] = leader_id
            else:
                self.group_leaders[group_id] = group_members[0] if group_members else None

        self._append_log("[编队] 最新成员分布：")
        for group_id in range(4):
            members_line = ", ".join(str(m) for m in self.group_assignments[group_id]) or "无"
            leader_id = self.group_leaders[group_id]
            leader_line = f"队长 #{leader_id}" if leader_id is not None else "队长未设定"
            self._append_log(
                f"  - {MonitorPage.GROUP_LABELS[group_id]}: {members_line} ({leader_line})"
            )

        self.assignment_page.load_assignments(self.group_assignments, self.group_leaders)

        for group_id, members_list in self.group_assignments.items():
            leader_id = self.group_leaders[group_id]
            for drone_id in members_list:
                self._send_config_update(drone_id, group_id, drone_id == leader_id)

    def on_close(self):
        try:
            self.bridge.stop()
        except Exception:
            pass
        self.destroy()


def main():
    app = GroundControlApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
