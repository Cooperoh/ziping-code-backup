import tkinter as tk
from tkinter import ttk


class FormationAssignmentPage(ttk.Frame):
    """编队管理页：支持拖拽、点击与快捷编组。"""

    GROUP_TITLES = {
        0: "编队0",
        1: "编队1",
        2: "编队2",
        3: "编队3",
    }

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        self.groups: dict[int, list[int]] = {gid: [] for gid in self.GROUP_TITLES}
        self.leaders: dict[int, int | None] = {gid: None for gid in self.GROUP_TITLES}

        self.group_frames: dict[int, ttk.LabelFrame] = {}
        self.group_canvases: dict[int, tk.Canvas] = {}
        self.group_bodies: dict[int, tk.Frame] = {}
        self.group_tiles: dict[int, dict[int, ttk.Label]] = {gid: {} for gid in self.GROUP_TITLES}

        self._drag_payload: tuple[int, int] | None = None
        self._drag_start: tuple[int, int] | None = None

        self._build_ui()
        for group_id in self.GROUP_TITLES:
            self._refresh_group(group_id)

    # --------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=6, pady=6)

        top = ttk.Frame(main)
        top.pack(fill="both", expand=True)
        for col in range(3):
            top.columnconfigure(col, weight=1, uniform="top")

        for index, group_id in enumerate((1, 2, 3)):
            frame, canvas, body = self._create_zone(top)
            frame.grid(row=0, column=index, sticky="nsew", padx=4, pady=4)
            self.group_frames[group_id] = frame
            self.group_canvases[group_id] = canvas
            self.group_bodies[group_id] = body

        bottom = ttk.Frame(main)
        bottom.pack(fill="both", expand=True)
        bottom.columnconfigure(0, weight=1)

        pool_frame, pool_canvas, pool_body = self._create_zone(bottom)
        pool_frame.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.group_frames[0] = pool_frame
        self.group_canvases[0] = pool_canvas
        self.group_bodies[0] = pool_body

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=6, pady=(0, 4))
        ttk.Label(
            footer,
            text="说明：编队0左键→编队1，右键→编队2，拖拽可投放到编队1/2/3；编队1~3左键直接回编队0。",
            foreground="#5a6b85",
        ).pack(side="left")
        ttk.Button(footer, text="发布编队调整", command=self._handle_upload).pack(side="right")

    def _create_zone(self, parent: tk.Misc) -> tuple[ttk.LabelFrame, tk.Canvas, tk.Frame]:
        frame = ttk.LabelFrame(parent, text="")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        canvas = tk.Canvas(frame, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        body = tk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        def _sync_width(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        body.bind("<Configure>", lambda _evt: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", _sync_width)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        return frame, canvas, body

    # ------------------------------------------------------------- roster sync
    def update_drone_roster(self, drone_ids) -> None:
        updated = False
        for drone_id in drone_ids:
            if not self._contains_drone(drone_id):
                self.groups[0].append(drone_id)
                updated = True
        if updated:
            self.groups[0].sort()
            self._ensure_leader(0)
            self._refresh_group(0)

    def load_assignments(self, members, leaders) -> None:
        for group_id in self.GROUP_TITLES:
            values = sorted(set(members.get(group_id, [])))
            self.groups[group_id] = values
            if group_id == 0 or not values:
                self.leaders[group_id] = None
            else:
                self.leaders[group_id] = min(values)
            self._refresh_group(group_id)

    def _contains_drone(self, drone_id: int) -> bool:
        return any(drone_id in members for members in self.groups.values())

    # -------------------------------------------------------------- operations
    def _assign_to_group(self, drone_id: int, group_id: int) -> None:
        source_group = None
        for gid, members in self.groups.items():
            if drone_id in members:
                members.remove(drone_id)
                source_group = gid
                break
        if drone_id not in self.groups[group_id]:
            self.groups[group_id].append(drone_id)
        self.groups[group_id].sort()

        for gid in filter(lambda g: g is not None, (source_group, group_id)):
            self._ensure_leader(gid)  # type: ignore[arg-type]
            self._refresh_group(gid)  # type: ignore[arg-type]

    def _ensure_leader(self, group_id: int | None) -> None:
        if group_id is None or group_id not in self.leaders:
            return
        members = self.groups[group_id]
        self.leaders[group_id] = min(members) if members else None

    # --------------------------------------------------------------- drag & click
    def _on_tile_press(self, event: tk.Event) -> None:
        tile: ttk.Label = event.widget  # type: ignore[assignment]
        self._drag_payload = (tile.drone_id, tile.group_id)  # type: ignore[attr-defined]
        self._drag_start = (event.x_root, event.y_root)

    def _on_tile_motion(self, event: tk.Event) -> None:
        if not self._drag_payload or self._drag_start is None:
            return
        sx, sy = self._drag_start
        if abs(event.x_root - sx) > 3 or abs(event.y_root - sy) > 3:
            self._drag_start = None

    def _on_tile_release(self, event: tk.Event) -> None:
        if not self._drag_payload:
            return
        drone_id, source_group = self._drag_payload
        target = self._resolve_group_from_coords(event.x_root, event.y_root)
        moved = self._drag_start is None

        if moved and target is not None and target != source_group:
            if source_group == 0 and target in (1, 2, 3):
                self._assign_to_group(drone_id, target)
            elif source_group in (1, 2, 3) and target in (0, 1, 2, 3):
                self._assign_to_group(drone_id, target)
        else:
            if source_group == 0:
                self._assign_to_group(drone_id, 1)
            else:
                self._assign_to_group(drone_id, 0)

        self._drag_payload = None
        self._drag_start = None

    def _on_tile_right_click(self, group_id: int, drone_id: int) -> None:
        if group_id == 0:
            self._assign_to_group(drone_id, 2)
        else:
            self._assign_to_group(drone_id, 0)

    def _resolve_group_from_coords(self, x_root: int, y_root: int) -> int | None:
        widget = self.winfo_containing(x_root, y_root)
        while widget is not None:
            for gid, body in self.group_bodies.items():
                if widget is body:
                    return gid
            for gid, canvas in self.group_canvases.items():
                if widget is canvas:
                    return gid
            for gid, frame in self.group_frames.items():
                if widget is frame:
                    return gid
            widget = widget.master if hasattr(widget, "master") else None
        return None

    # ------------------------------------------------------------- data export
    def export_members(self) -> dict[int, list[int]]:
        return {gid: list(self.groups[gid]) for gid in self.GROUP_TITLES}

    def export_leaders(self) -> dict[int, int | None]:
        return dict(self.leaders)

    def _handle_upload(self) -> None:
        self.app.on_assignments_uploaded(self.export_members(), self.export_leaders())

    # -------------------------------------------------------------- rendering
    def _columns_for_group(self, group_id: int) -> int:
        return 6 if group_id == 0 else 3

    def _refresh_group(self, group_id: int) -> None:
        body = self.group_bodies[group_id]
        for child in body.winfo_children():
            child.destroy()
        self.group_tiles[group_id].clear()

        columns = self._columns_for_group(group_id)
        for col in range(columns):
            body.grid_columnconfigure(col, weight=1)

        members = sorted(self.groups[group_id])
        for index, drone_id in enumerate(members):
            tile = self._create_tile(body, group_id, drone_id)
            row = index // columns
            col = index % columns
            tile.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            self.group_tiles[group_id][drone_id] = tile

        self._update_group_title(group_id)
        self._update_scrollregion(group_id)

    def _create_tile(self, parent: tk.Frame, group_id: int, drone_id: int) -> ttk.Label:
        tile = ttk.Label(parent, text=f"#{drone_id+1}", relief="ridge", padding=(6, 4))
        tile.configure(cursor="hand2")
        tile.group_id = group_id  # type: ignore[attr-defined]
        tile.drone_id = drone_id  # type: ignore[attr-defined]
        tile.bind("<ButtonPress-1>", self._on_tile_press, add="+")
        tile.bind("<B1-Motion>", self._on_tile_motion, add="+")
        tile.bind("<ButtonRelease-1>", self._on_tile_release, add="+")
        tile.bind("<Button-3>", lambda _evt, g=group_id, d=drone_id: self._on_tile_right_click(g, d), add="+")
        return tile

    def _update_group_title(self, group_id: int) -> None:
        count = len(self.groups[group_id])
        base = self.GROUP_TITLES[group_id]
        leader_id = self.leaders.get(group_id)
        if leader_id is not None:
            title = f"{base}（{count}） 队长：#{leader_id+1}"
        else:
            title = f"{base}（{count}） 队长：未设定"
        self.group_frames[group_id].configure(text=title)

    def _update_scrollregion(self, group_id: int) -> None:
        canvas = self.group_canvases[group_id]
        canvas.configure(scrollregion=canvas.bbox("all"))
