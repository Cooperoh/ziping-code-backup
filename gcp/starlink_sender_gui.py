import tkinter as tk
from tkinter import messagebox, ttk

from starlink_sender import send_starlink_sim

DEFAULT_LAT = "38.31838"
DEFAULT_LON = "117.680"


class StarlinkSenderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Starlink Sender")
        self.geometry("300x200")
        self.resizable(False, False)

        self.lat_var = tk.StringVar(value=DEFAULT_LAT)
        self.lon_var = tk.StringVar(value=DEFAULT_LON)
        self.status_var = tk.StringVar(value="Ready.")

        self._build_ui()

    def _build_ui(self):
        main = ttk.Frame(self, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(1, weight=1)

        ttk.Label(main, text="Latitude").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(main, textvariable=self.lat_var, width=20).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(main, text="Longitude").grid(row=1, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(main, textvariable=self.lon_var, width=20).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        btn_row = ttk.Frame(main)
        btn_row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 8))
        ttk.Button(btn_row, text="Send", command=self._on_send).pack(side="left")
        ttk.Button(btn_row, text="Reset", command=self._on_reset).pack(side="left", padx=(8, 0))

        ttk.Label(main, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky="w")

    def _on_reset(self):
        self.lat_var.set(DEFAULT_LAT)
        self.lon_var.set(DEFAULT_LON)
        self.status_var.set("Ready.")

    def _on_send(self):
        try:
            lat = float(self.lat_var.get().strip())
            lon = float(self.lon_var.get().strip())
        except ValueError:
            messagebox.showerror("Input Error", "Latitude and longitude must be numbers.")
            return

        try:
            count = send_starlink_sim(lat, lon)
        except OSError as exc:
            messagebox.showerror("Send Failed", f"Failed to send UDP command: {exc}")
            return

        self.status_var.set(f"Sent to {count} address(es).")


def main():
    app = StarlinkSenderApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
