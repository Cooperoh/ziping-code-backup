import math
import random
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import cast

import tkintermapview
from PIL import Image, ImageDraw, ImageTk


class StarlinkPage(ttk.Frame):
    """Starlink page mirrors monitor UI with simulated target upload workflow."""

    GROUP_LABELS = {
        0: "编队0",
        1: "编队1",
        2: "编队2",
        3: "编队3",
    }

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        self.show_tracks_flag = tk.BooleanVar(value=True)
        self.show_goto_flag = tk.BooleanVar(value=True)
        self._tree_sort_reverse = False
        self._tree_id_label = "ID"
        self._pending_focus_options = ["None"]

        # Map state caches
        self.markers = {}
        self.paths = {}
        self.goto_paths = {}
        self.goto_markers = {}
        self.goto_icon = self._create_goto_icon()

        self.group_selection = tk.IntVar(value=-1)

        self.coord_var = tk.StringVar(value="")
        self._sim_location = None
        self._sim_marker = None

        self._build_ui()

    # --------------------------------------------------------------------- UI
    def _build_ui(self):
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=8, pady=8)
        main.columnconfigure(0, weight=4, uniform="layout")
        main.columnconfigure(1, weight=3, uniform="layout")
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew")

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        map_frame = ttk.LabelFrame(left, text="OpenStreetMap")
        map_frame.pack(fill="both", expand=True)
        self.map = tkintermapview.TkinterMapView(map_frame, corner_radius=8)
        self.map.pack(fill="both", expand=True)

        tool = ttk.Frame(map_frame)
        tool.place(relx=1.0, rely=0.0, anchor="ne")
        self.drone_focus = ttk.Combobox(
            tool,
            state="readonly",
            values=self._pending_focus_options,
            width=8,
        )
        self.drone_focus.pack(side="left", padx=2, pady=2)
        self.drone_focus.set(self._pending_focus_options[0])
        ttk.Checkbutton(tool, text="期望点", variable=self.show_goto_flag, command=self.toggle_goto).pack(side="left", padx=2, pady=2)
        ttk.Button(tool, text="清除期望点", command=self.clear_goto).pack(side="left", padx=2, pady=2)
        ttk.Button(tool, text="显示轨迹", command=self.show_tracks).pack(side="left", padx=2, pady=2)
        ttk.Button(tool, text="隐藏轨迹", command=self.hide_tracks).pack(side="left", padx=2, pady=2)
        ttk.Button(tool, text="清除轨迹", command=self.clear_tracks).pack(side="left", padx=2, pady=2)

        ctrl = ttk.LabelFrame(left, text="指挥功能")
        ctrl.pack(fill="x", pady=(6, 0))

        actions_row = ttk.Frame(ctrl)
        actions_row.pack(fill="x", padx=6, pady=4)
        ttk.Button(actions_row, text="起飞", command=lambda: self._dispatch_basic("takeoff")).pack(side="left", padx=4)
        ttk.Button(actions_row, text="返航", command=lambda: self._dispatch_basic("rtl")).pack(side="left", padx=4)
        ttk.Button(actions_row, text="降落", command=lambda: self._dispatch_basic("land")).pack(side="left", padx=4)

        coord_row = ttk.Frame(ctrl)
        coord_row.pack(fill="x", padx=6, pady=4)
        ttk.Label(coord_row, text="坐标信息").pack(side="left", padx=(12, 6))
        self.coord_entry = ttk.Entry(coord_row, textvariable=self.coord_var, width=28, state="readonly")
        self.coord_entry.pack(side="left", padx=6)
        ttk.Button(coord_row, text="模拟信息传输", command=self.simulate_transfer).pack(side="left", padx=(20, 4))

        command_row = ttk.Frame(ctrl)
        command_row.pack(fill="x", padx=6, pady=4)
        ttk.Button(command_row, text="指令拒绝", command=self.reject_command).pack(side="left", padx=4)
        self.confirm_button = ttk.Button(command_row, text="指令确认", command=self.confirm_command, state="disabled")
        self.confirm_button.pack(side="left", padx=4)
        self.upload_button = ttk.Button(command_row, text="指令上传", command=self.upload_command, state="disabled")
        self.upload_button.pack(side="left", padx=4)

        group_frame = ttk.LabelFrame(ctrl, text="控制目标")
        group_frame.pack(fill="x", padx=6, pady=4)
        for group_id in range(4):
            ttk.Radiobutton(
                group_frame,
                text=self.GROUP_LABELS[group_id],
                variable=self.group_selection,
                value=group_id,
            ).pack(side="left", padx=4)

        log_frame = ttk.LabelFrame(right, text="事件日志")
        log_frame.pack(fill="both", expand=True)

        log_toolbar = ttk.Frame(log_frame)
        log_toolbar.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Button(log_toolbar, text="清除日志", command=self.clear_log).pack(side="left")
        ttk.Button(log_toolbar, text="导出日志", command=self.export_log).pack(side="left", padx=(6, 0))

        log_container = ttk.Frame(log_frame)
        log_container.pack(fill="both", expand=True, padx=6, pady=6)
        self.log = tk.Text(log_container, height=30, state="disabled", wrap="word")
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_container, orient="vertical", command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)

        table = ttk.LabelFrame(right, text="监测信息")
        table.pack(fill="both", expand=True, pady=(6, 0))
        columns = ("id", "tag", "speed", "heading", "err")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", height=20)
        self.tree.column("id", width=50, anchor="center")
        self.tree.heading("id", text="ID ASC", command=self.toggle_id_sort)
        self.tree.column("tag", width=120, anchor="center")
        self.tree.heading("tag", text="标签")
        self.tree.column("speed", width=80, anchor="center")
        self.tree.heading("speed", text="速度")
        self.tree.column("heading", width=80, anchor="center")
        self.tree.heading("heading", text="航向")
        self.tree.column("err", width=80, anchor="center")
        self.tree.heading("err", text="误差")
        self.tree.pack(fill="both", expand=True, padx=6, pady=6)

    # ------------------------------------------------------------------ events
    def _dispatch_basic(self, command):
        self.app.handle_basic_command(command)

    # ----------------------------------------------------------------- logging
    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", f"{text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def export_log(self):
        content = self.log.get("1.0", "end").strip()
        if not content:
            messagebox.showinfo("导出日志", "暂无日志可导出。")
            return
        file_path = filedialog.asksaveasfilename(
            parent=self,
            title="导出日志",
            defaultextension=".txt",
            filetypes=[("文本文档", "*.txt"), ("所有文件", "*.*")],
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as handle:
                handle.write(content + "\n")
        except OSError as exc:
            messagebox.showerror("导出日志", f"写入文件失败：{exc}")
        else:
            messagebox.showinfo("导出日志", f"日志已保存到：\n{file_path}")

    # ------------------------------------------------------------ simulation
    def _reset_target_state(self):
        if self._sim_marker is not None:
            try:
                self._sim_marker.delete()
            except Exception:
                pass
        self._sim_marker = None
        self._sim_location = None
        self.coord_var.set("")
        self.confirm_button.state(["disabled"])
        self.upload_button.state(["disabled"])

    def handle_starlink_report(self, report):
        status = report.get("status")
        if status != "ok":
            error = report.get("error")
            drone_id = report.get("id")
            tag = report.get("tag")
            source = report.get("source")
            self._reset_target_state()
            details = []
            if error:
                details.append(f"error={error}")
            if tag:
                details.append(tag)
            elif drone_id is not None:
                details.append(f"id={drone_id}")
            if source:
                details.append(f"source={source}")
            extra = " ".join(details)
            if extra:
                self.append_log(f"[Starlink] report {status} {extra}")
            else:
                self.append_log(f"[Starlink] report {status}")
            return

        lat = report.get("lat")
        lon = report.get("lon")
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            self._reset_target_state()
            self.append_log("[Starlink] report invalid coordinates")
            return

        self._sim_location = (lat, lon)
        self.coord_var.set(f"{lat:.6f}, {lon:.6f}")
        self._place_sim_marker(lat, lon)
        self.confirm_button.state(["!disabled"])
        self.upload_button.state(["disabled"])

        drone_id = report.get("id")
        tag = report.get("tag")
        source = report.get("source")
        latency_ms = report.get("latency_ms")
        received_at = report.get("received_at")
        parsed_at = report.get("parsed_at")
        details = []
        if tag:
            details.append(tag)
        elif drone_id is not None:
            details.append(f"id={drone_id}")
        if source:
            details.append(f"source={source}")
        if isinstance(latency_ms, (int, float)):
            details.append(f"latency={latency_ms}ms")
        if received_at:
            details.append(f"recv={received_at}")
        if parsed_at:
            details.append(f"parsed={parsed_at}")
        extra = " ".join(details)
        if extra:
            self.append_log(f"[Starlink] report ok {lat:.6f}, {lon:.6f} {extra}")
        else:
            self.append_log(f"[Starlink] report ok {lat:.6f}, {lon:.6f}")

    def simulate_transfer(self):
        start_time = time.perf_counter()
        try:
            home_lat, home_lon = self.app.get_home_location()
        except AttributeError:
            home_lat, home_lon = 0.0, 0.0
        # lat = home_lat + random.uniform(-0.02, 0.02)
        # lon = home_lon + random.uniform(-0.02, 0.02)
        lat = 38.31838 # north of home 1000 meters
        lon = home_lon


        self._sim_location = (lat, lon)
        self.coord_var.set(f"{lat:.6f}, {lon:.6f}")
        self._place_sim_marker(lat, lon)

        self.confirm_button.state(["!disabled"])
        self.upload_button.state(["disabled"])
        self.append_log(f"[Starlink] 收到模拟坐标：{lat:.6f}, {lon:.6f}")
        elapsed_ms = (time.perf_counter() - start_time) * 3000.0
        self.append_log(f"[Starlink] 模拟信息处理耗时：{elapsed_ms:.2f} ms")

    def _place_sim_marker(self, lat, lon):
        if self._sim_marker is not None:
            try:
                self._sim_marker.delete()
            except Exception:
                pass
            self._sim_marker = None
        try:
            self._sim_marker = self.map.set_marker(lat, lon, text="Starlink目标")
        except Exception:
            self._sim_marker = None
        try:
            self.map.set_position(lat, lon)
        except Exception:
            pass

    def reject_command(self):
        self._reset_target_state()
        self.append_log("[Starlink] 指令已拒绝，清除目标。")

    def confirm_command(self):
        if not self._sim_location:
            self.append_log("[Starlink] 未选择坐标，无法确认。")
            return
        self.upload_button.state(["!disabled"])
        self.append_log("[Starlink] 指令已确认，可执行上传。")

    def upload_command(self):
        if not self._sim_location:
            self.append_log("[Starlink] 未选择坐标，无法上传。")
            return
        lat, lon = self._sim_location
        self.app.send_starlink_location(self._sim_location)
        self.upload_button.state(["disabled"])
        self.confirm_button.state(["disabled"])
        self.append_log(f"[Starlink] 已上传目标坐标：{lat:.6f}, {lon:.6f}")

    # ------------------------------------------------------------ group access
    def get_selected_group(self):
        value = self.group_selection.get()
        return value if value in self.GROUP_LABELS else None

    # ---------------------------------------------------------- focus options
    def set_focus_options(self, drone_ids):
        new_values = ["None"] + [str(d) for d in sorted(drone_ids)]
        if new_values != self._pending_focus_options:
            self._pending_focus_options = new_values
            current = self.drone_focus.get()
            self.drone_focus.configure(values=new_values)
            self.drone_focus.set(current if current in new_values else new_values[0])
        elif self.drone_focus.get() not in new_values:
            self.drone_focus.set(new_values[0])

    # ------------------------------------------------------------------ tracks
    def rebuild_all_paths(self):
        for pid in list(self.paths.keys()):
            try:
                self.paths[pid].delete()
            except Exception:
                pass
        self.paths.clear()

    def show_tracks(self):
        self.show_tracks_flag.set(True)
        self.rebuild_all_paths()
        self.append_log("[轨迹] 显示")

    def hide_tracks(self):
        self.show_tracks_flag.set(False)
        for pid in list(self.paths.keys()):
            try:
                self.paths[pid].delete()
            except Exception:
                pass
            self.paths.pop(pid, None)
        self.append_log("[轨迹] 隐藏")

    def clear_tracks(self):
        for pid in list(self.paths.keys()):
            try:
                self.paths[pid].delete()
            except Exception:
                pass
        self.paths.clear()
        self.app.clear_tracks_history()
        self.append_log("[轨迹] 清除")

    def clear_goto_overlays(self):
        for drone_id in list(set(self.goto_paths.keys()) | set(self.goto_markers.keys())):
            self._clear_goto_overlay(drone_id)

    def toggle_goto(self):
        if self.show_goto_flag.get():
            self.append_log("[Goto] 显示")
        else:
            self.clear_goto_overlays()
            self.append_log("[Goto] 隐藏")

    def clear_goto(self):
        self.app.clear_goto_targets()
        self.append_log("[Goto] 清除")

    # ------------------------------------------------------------- tree sorting
    def toggle_id_sort(self):
        self._tree_sort_reverse = not self._tree_sort_reverse
        self._update_id_heading()

    def _update_id_heading(self):
        label = f"{self._tree_id_label} {'DESC' if self._tree_sort_reverse else 'ASC'}"
        self.tree.heading("id", text=label, command=self.toggle_id_sort)

    def _create_goto_icon(self):
        size = 18
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((2, 2, size - 3, size - 3), fill="#FFD400", outline="#A67C00", width=2)
        return ImageTk.PhotoImage(image)

    def _clear_goto_overlay(self, drone_id):
        goto_path = self.goto_paths.pop(drone_id, None)
        if goto_path is not None:
            try:
                goto_path.delete()
            except Exception:
                pass
        goto_marker = self.goto_markers.pop(drone_id, None)
        if goto_marker is not None:
            try:
                goto_marker.delete()
            except Exception:
                pass

    def _sync_goto_overlay(self, drone_id, lat, lon, goto_lat, goto_lon):
        goto_marker = self.goto_markers.get(drone_id)
        if goto_marker is None:
            try:
                self.goto_markers[drone_id] = self.map.set_marker(
                    goto_lat,
                    goto_lon,
                    text=cast(str, None),
                    icon=self.goto_icon,
                    icon_anchor="center",
                )
            except Exception:
                pass
        else:
            try:
                goto_marker.set_position(goto_lat, goto_lon)
            except Exception:
                self._clear_goto_overlay(drone_id)
                try:
                    self.goto_markers[drone_id] = self.map.set_marker(
                        goto_lat,
                        goto_lon,
                        text=cast(str,None),
                        icon=self.goto_icon,
                        icon_anchor="center",
                    )
                except Exception:
                    pass

        if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))):
            goto_path = self.goto_paths.pop(drone_id, None)
            if goto_path is not None:
                try:
                    goto_path.delete()
                except Exception:
                    pass
            return

        line_points = [(lat, lon), (goto_lat, goto_lon)]
        goto_path = self.goto_paths.get(drone_id)
        if goto_path is None:
            try:
                self.goto_paths[drone_id] = self.map.set_path(
                    line_points,
                    color="#FFD400",
                    width=4,
                )
            except Exception:
                pass
        else:
            try:
                goto_path.set_position_list(line_points)
            except Exception:
                path_deleted = self.goto_paths.pop(drone_id, None)
                if path_deleted is not None:
                    try:
                        path_deleted.delete()
                    except Exception:
                        pass
                try:
                    self.goto_paths[drone_id] = self.map.set_path(
                        line_points,
                        color="#FFD400",
                        width=4,
                    )
                except Exception:
                    pass

    # -------------------------------------------------------------- ui refresh
    def refresh(self, state, tracks, show_errors):
        items = sorted(
            state.items(),
            key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else kv[0],
            reverse=self._tree_sort_reverse,
        )
        drone_ids = [int(k) for k, _ in items if str(k).isdigit()]
        self.set_focus_options(drone_ids)

        for drone_id, data in items:
            lat = data.get("lat")
            lon = data.get("lon")
            goto_lat = data.get("goto_lat")
            goto_lon = data.get("goto_lon")
            tag = data.get("tag") or f"DRONE{drone_id}"
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                if drone_id not in self.markers:
                    self.markers[drone_id] = self.map.set_marker(lat, lon, text=tag)
                else:
                    try:
                        self.markers[drone_id].set_position(lat, lon)
                        self.markers[drone_id].set_text(tag)
                    except Exception:
                        self.markers[drone_id] = self.map.set_marker(lat, lon, text=tag)
                if self.show_tracks_flag.get():
                    pts = tracks.get(drone_id, [])
                    if pts:
                        if drone_id in self.paths:
                            try:
                                self.paths[drone_id].delete()
                            except Exception:
                                pass
                        try:
                            self.paths[drone_id] = self.map.set_path(pts)
                        except Exception:
                            pass

            if self.show_goto_flag.get() and isinstance(goto_lat, (int, float)) and isinstance(goto_lon, (int, float)):
                self._sync_goto_overlay(drone_id, lat, lon, goto_lat, goto_lon)
            else:
                self._clear_goto_overlay(drone_id)

        current_iids = set(self.tree.get_children(""))
        desired_order = []
        for drone_id, data in items:
            iid = str(drone_id)
            desired_order.append(iid)
            tag = data.get("tag") or f"DRONE{drone_id}"
            speed = data.get("speed")
            heading = data.get("heading")
            err_s = data.get("err_s")
            err_d = data.get("err_d")
            err = ""
            if show_errors:
                if isinstance(err_s, (int, float)) and isinstance(err_d, (int, float)):
                    err = f"{math.hypot(err_s, err_d):.1f}"
                elif isinstance(err_s, (int, float)):
                    err = f"{abs(err_s):.1f}"
            values = (
                drone_id,
                tag,
                f"{speed:.1f}" if isinstance(speed, (int, float)) else "",
                f"{heading:.0f}" if isinstance(heading, (int, float)) else "",
                err,
            )
            if iid in current_iids:
                self.tree.item(iid, values=values)
            else:
                self.tree.insert("", "end", iid=iid, values=values)

            try:
                focus_value = self.drone_focus.get()
                if focus_value != "None" and int(focus_value) == int(drone_id):
                    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                        self.map.set_position(lat, lon)
            except Exception:
                pass

        for iid in current_iids - set(desired_order):
            self.tree.delete(iid)
        for index, iid in enumerate(desired_order):
            try:
                self.tree.move(iid, "", index)
            except Exception:
                pass
