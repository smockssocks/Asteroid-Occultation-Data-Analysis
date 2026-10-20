"""Point-and-click front end for downloading occultation data with bbftp.

Run with:  python download_gui.py

Fill in the dates and a destination folder, check the elog, then press
"Start download". Settings are remembered in ~/.ao_download_gui.json.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, scrolledtext, ttk

import bbftp_download as bd

SETTINGS_PATH = os.path.expanduser("~/.ao_download_gui.json")
PREFIX_LETTERS = "TUGHJ"


class DownloadApp(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=10)
        self.master = master
        self.log_queue: queue.Queue[str | tuple] = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None

        self.user = tk.StringVar(value=bd.DEFAULT_USER)
        self.server = tk.StringVar(value=bd.DEFAULT_SERVER)
        self.remote_root = tk.StringVar(value=bd.DEFAULT_REMOTE_ROOT)
        self.bbftp = tk.StringVar(value=shutil.which("bbftp") or "bbftp")
        self.ssh_batch = tk.BooleanVar(value=True)
        self.verbose = tk.BooleanVar(value=True)
        self.dest = tk.StringVar(value=os.path.expanduser("~/AO/data"))
        self.prefix_vars = {c: tk.BooleanVar(value=True) for c in PREFIX_LETTERS}
        self.extra_prefixes = tk.StringVar()
        self.elog_checked = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready.")

        self._build()
        self._load_settings()
        self.master.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_log)

    # ---------- layout ----------
    def _build(self) -> None:
        self.grid(sticky="nsew")
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        conn = ttk.LabelFrame(self, text="1. Connection (UCLA archive)", padding=8)
        conn.grid(row=0, column=0, sticky="ew")
        conn.columnconfigure(1, weight=1)
        self._row(conn, 0, "Username:", self.user)
        self._row(conn, 1, "Server:", self.server)
        self._row(conn, 2, "Remote data folder:", self.remote_root)
        self._row(conn, 3, "bbftp program:", self.bbftp, browse=self._browse_bbftp)
        opts = ttk.Frame(conn)
        opts.grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(opts, text="SSH batch login (-S, uses your SSH key)", variable=self.ssh_batch).pack(side="left")
        ttk.Checkbutton(opts, text="Verbose (-V)", variable=self.verbose).pack(side="left", padx=10)
        ttk.Label(conn, foreground="gray",
                  text="No password box: bbftp logs in with the SSH key you set up for the archive.").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))

        data = ttk.LabelFrame(self, text="2. What to download", padding=8)
        data.grid(row=1, column=0, sticky="ew", pady=8)
        data.columnconfigure(1, weight=1)
        ttk.Label(data, text="Dates (UT):").grid(row=0, column=0, sticky="nw")
        self.dates_text = tk.Text(data, height=3, width=40)
        self.dates_text.grid(row=0, column=1, columnspan=2, sticky="ew")
        self.dates_text.insert("1.0", "20250420, 20250421")
        ttk.Label(data, foreground="gray",
                  text="YYYYMMDD, separated by commas/spaces/new lines. Ranges: 20250420-20250425").grid(
            row=1, column=1, columnspan=2, sticky="w")

        ttk.Label(data, text="File prefixes:").grid(row=2, column=0, sticky="w", pady=(6, 0))
        pf = ttk.Frame(data)
        pf.grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))
        for c, var in self.prefix_vars.items():
            ttk.Checkbutton(pf, text=c, variable=var).pack(side="left")
        ttk.Label(pf, text="   other letters:").pack(side="left")
        ttk.Entry(pf, textvariable=self.extra_prefixes, width=8).pack(side="left")

        self._row(data, 3, "Save to folder:", self.dest, browse=self._browse_dest)

        elog = ttk.Frame(data)
        elog.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(elog, text="Open elog", command=lambda: webbrowser.open(bd.ELOG_URL)).pack(side="left")
        ttk.Checkbutton(elog, text="I checked the elog: the target was observed and files are named correctly",
                        variable=self.elog_checked).pack(side="left", padx=8)

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, sticky="ew")
        ttk.Button(btns, text="Preview commands", command=self._preview).pack(side="left")
        self.start_btn = ttk.Button(btns, text="Start download", command=self._start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(btns, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Button(btns, text="Clear log", command=lambda: self.log_box.delete("1.0", "end")).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(self, height=18, width=100, font=("Courier", 9))
        self.log_box.grid(row=3, column=0, sticky="nsew", pady=(8, 4))
        self.rowconfigure(3, weight=1)
        ttk.Label(self, textvariable=self.status, anchor="w").grid(row=4, column=0, sticky="ew")

    def _row(self, parent, row, label, var, browse=None) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=2)
        if browse:
            ttk.Button(parent, text="Browse…", command=browse).grid(row=row, column=2, padx=(4, 0))

    def _browse_dest(self) -> None:
        path = filedialog.askdirectory(initialdir=self.dest.get() or os.path.expanduser("~"))
        if path:
            self.dest.set(path)

    def _browse_bbftp(self) -> None:
        path = filedialog.askopenfilename(title="Find the bbftp executable")
        if path:
            self.bbftp.set(path)

    # ---------- actions ----------
    def _collect(self) -> tuple[list[str], str, bd.DownloadOptions]:
        dates = bd.parse_dates(self.dates_text.get("1.0", "end"))
        if not dates:
            raise ValueError("Enter at least one date.")
        dest = self.dest.get().strip()
        if not dest:
            raise ValueError("Choose a folder to save the data in.")
        letters = "".join(c for c, v in self.prefix_vars.items() if v.get()) + self.extra_prefixes.get()
        opts = bd.DownloadOptions(
            user=self.user.get().strip(), server=self.server.get().strip(),
            remote_root=self.remote_root.get().strip(), prefixes=bd.normalize_prefixes(letters),
            bbftp=self.bbftp.get().strip() or "bbftp", verbose=self.verbose.get(), ssh_batch=self.ssh_batch.get())
        if not opts.user or not opts.server:
            raise ValueError("Username and server can't be empty.")
        return dates, dest, opts

    def _preview(self) -> None:
        try:
            dates, dest, opts = self._collect()
        except ValueError as e:
            messagebox.showerror("Check your inputs", str(e))
            return
        self._log(f"--- Preview: {len(dates)} date(s) ---")
        for day in dates:
            self._log(bd.format_command(bd.build_command(day, dest, opts)))

    def _start(self) -> None:
        try:
            dates, dest, opts = self._collect()
        except ValueError as e:
            messagebox.showerror("Check your inputs", str(e))
            return
        if not shutil.which(opts.bbftp):
            messagebox.showerror("bbftp not found",
                                 f"Couldn't find '{opts.bbftp}'. Install the bbftp client and set up your "
                                 "machine for the UCLA archive, or use Browse… to point at the program.")
            return
        if not self.elog_checked.get() and not messagebox.askyesno(
                "Elog not checked",
                "You haven't ticked the elog box. Files are sometimes named incorrectly, so check the elog "
                "before downloading.\n\nDownload anyway?"):
            return
        self._save_settings()
        self.stop_event.clear()
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status.set(f"Downloading {len(dates)} date(s)…")
        self.worker = threading.Thread(target=self._work, args=(dates, dest, opts), daemon=True)
        self.worker.start()

    def _work(self, dates, dest, opts) -> None:
        try:
            results = bd.run_downloads(dates, dest, opts, log=self.log_queue.put, stop_event=self.stop_event)
        except Exception as e:  # report anything unexpected in the log instead of dying silently
            self.log_queue.put(f"ERROR: {e}")
            results = []
        self.log_queue.put(("done", results))

    def _stop(self) -> None:
        self.stop_event.set()
        self.status.set("Stopping…")

    def _finish(self, results: list[bd.DateResult]) -> None:
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        ok = [r for r in results if r.ok]
        bad = [r for r in results if not r.ok]
        self._log("=== Summary ===")
        for r in results:
            mark = "OK  " if r.ok else "FAIL"
            self._log(f"{mark} {r.date}: {len(r.files)} files, {bd.human_size(r.total_bytes)} -> {r.local_dir}")
        self.status.set(f"Finished: {len(ok)} succeeded, {len(bad)} failed.")
        if bad and not self.stop_event.is_set():
            messagebox.showwarning(
                "Some dates failed",
                "Some dates didn't download. Check the log, the elog, and your bbftp setup.\n\n"
                "If the target was observed, bbftp is set up, and it isn't the weekend, the ECM data may "
                "not be archived yet. Email Bill Hanlon and ask for it to be archived.")

    # ---------- log plumbing ----------
    def _log(self, line: str) -> None:
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")

    def _drain_log(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "done":
                    self._finish(item[1])
                else:
                    self._log(item)
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    # ---------- settings ----------
    def _load_settings(self) -> None:
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as fh:
                s = json.load(fh)
        except (OSError, ValueError):
            return
        for key in ("user", "server", "remote_root", "bbftp", "dest", "extra_prefixes"):
            if isinstance(s.get(key), str):
                getattr(self, key).set(s[key])
        for key in ("ssh_batch", "verbose"):
            if isinstance(s.get(key), bool):
                getattr(self, key).set(s[key])
        if isinstance(s.get("prefixes"), str):
            for c, v in self.prefix_vars.items():
                v.set(c in s["prefixes"])
        if isinstance(s.get("dates"), str) and s["dates"].strip():
            self.dates_text.delete("1.0", "end")
            self.dates_text.insert("1.0", s["dates"].strip())

    def _save_settings(self) -> None:
        s = {key: getattr(self, key).get() for key in
             ("user", "server", "remote_root", "bbftp", "dest", "extra_prefixes", "ssh_batch", "verbose")}
        s["prefixes"] = "".join(c for c, v in self.prefix_vars.items() if v.get())
        s["dates"] = self.dates_text.get("1.0", "end").strip()
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
                json.dump(s, fh, indent=2)
        except OSError:
            pass

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Download running", "A download is still running. Stop it and quit?"):
                return
            self.stop_event.set()
        self._save_settings()
        self.master.destroy()


def main() -> None:
    root = tk.Tk()
    root.title("Occultation Data Downloader")
    root.minsize(760, 560)
    DownloadApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
