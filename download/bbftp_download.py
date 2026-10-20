"""Download VERITAS occultation (.WDQ) data from the UCLA archive with bbftp.

This is the logic behind ``download_gui.py``. It can also be run on its own,
which is handy on a server with no display:

    python bbftp_download.py --dates 20250420 20250421 --dest ~/AO/data

It reproduces the bash script from the analysis instructions: for each date
it makes ``<dest>/<date>/`` and runs

    bbftp -V -S -u bbftp -e "mget /veritas/DATAQ/d<date>/<date>-[TUGHJ]* <dest>/<date>/" gamma1.astro.ucla.edu
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Iterable

DEFAULT_SERVER = "gamma1.astro.ucla.edu"
DEFAULT_USER = "bbftp"
DEFAULT_REMOTE_ROOT = "/veritas/DATAQ"
DEFAULT_PREFIXES = "TUGHJ"
ELOG_URL = "http://veritash.sao.arizona.edu:8081/"

_DATE_FMT = "%Y%m%d"
_RANGE_RE = re.compile(r"^(\d{8})(?:(?:-|\.\.|to)(\d{8}))?$")


@dataclass
class DownloadOptions:
    user: str = DEFAULT_USER
    server: str = DEFAULT_SERVER
    remote_root: str = DEFAULT_REMOTE_ROOT
    prefixes: str = DEFAULT_PREFIXES
    bbftp: str = "bbftp"
    verbose: bool = True
    ssh_batch: bool = True
    log_file: str | None = "bbftp_log.txt"


@dataclass
class DateResult:
    date: str
    returncode: int | None
    local_dir: str
    files: list[str] = field(default_factory=list)
    total_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and bool(self.files)


def _check_date(text: str) -> date:
    try:
        return datetime.strptime(text, _DATE_FMT).date()
    except ValueError:
        raise ValueError(f"'{text}' is not a valid YYYYMMDD date") from None


def parse_dates(text: str) -> list[str]:
    """Turn free text into a list of YYYYMMDD strings.

    Dates may be separated by commas, spaces or newlines, and a range can be
    written ``20250420-20250425`` (inclusive). Duplicates are dropped and the
    original order is kept.
    """
    # Collapse spaces around range separators so "A - B" stays one token.
    text = re.sub(r"\s*(-|\.\.|\bto\b)\s*", r"\1", text.strip())
    dates: list[str] = []
    for token in re.split(r"[\s,;]+", text):
        if not token:
            continue
        m = _RANGE_RE.match(token)
        if not m:
            raise ValueError(f"Could not read '{token}'. Use YYYYMMDD or YYYYMMDD-YYYYMMDD.")
        start = _check_date(m.group(1))
        end = _check_date(m.group(2)) if m.group(2) else start
        if end < start:
            raise ValueError(f"Range '{token}' ends before it starts")
        day = start
        while day <= end:
            s = day.strftime(_DATE_FMT)
            if s not in dates:
                dates.append(s)
            day += timedelta(days=1)
    return dates


def normalize_prefixes(prefixes: str) -> str:
    letters = "".join(dict.fromkeys(c.upper() for c in prefixes if c.isalpha()))
    if not letters:
        raise ValueError("Pick at least one file prefix (e.g. T, U, G, H, J)")
    return letters


def remote_pattern(day: str, prefixes: str, remote_root: str = DEFAULT_REMOTE_ROOT) -> str:
    root = remote_root.rstrip("/")
    return f"{root}/d{day}/{day}-[{normalize_prefixes(prefixes)}]*"


def local_dir_for(dest_root: str, day: str) -> str:
    return os.path.join(os.path.expanduser(dest_root), day)


def build_command(day: str, dest_root: str, opts: DownloadOptions) -> list[str]:
    local = os.path.join(local_dir_for(dest_root, day), "")  # trailing separator
    cmd = [opts.bbftp]
    if opts.verbose:
        cmd.append("-V")
    if opts.ssh_batch:
        cmd.append("-S")
    cmd += ["-u", opts.user,
            "-e", f"mget {remote_pattern(day, opts.prefixes, opts.remote_root)} {local}",
            opts.server]
    return cmd


def format_command(cmd: list[str]) -> str:
    return shlex.join(cmd)


def _list_files(path: str) -> tuple[list[str], int]:
    if not os.path.isdir(path):
        return [], 0
    names = sorted(n for n in os.listdir(path) if os.path.isfile(os.path.join(path, n)))
    return names, sum(os.path.getsize(os.path.join(path, n)) for n in names)


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _kill(proc: subprocess.Popen) -> None:
    # bbftp starts ssh as a child, so kill the whole process group on POSIX.
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, PermissionError):
        pass


def run_downloads(
    dates: Iterable[str],
    dest_root: str,
    opts: DownloadOptions,
    log: Callable[[str], None] = print,
    stop_event: threading.Event | None = None,
) -> list[DateResult]:
    """Run bbftp once per date, streaming its output to ``log``.

    Output is also appended to ``opts.log_file`` (relative paths are placed in
    ``dest_root``). Setting ``stop_event`` kills the running transfer and
    skips the remaining dates.
    """
    dest_root = os.path.expanduser(dest_root)
    os.makedirs(dest_root, exist_ok=True)
    log_fh = None
    if opts.log_file:
        log_path = opts.log_file if os.path.isabs(opts.log_file) else os.path.join(dest_root, opts.log_file)
        log_fh = open(log_path, "a", encoding="utf-8")

    def emit(line: str) -> None:
        log(line)
        if log_fh:
            log_fh.write(line + "\n")
            log_fh.flush()

    results: list[DateResult] = []
    try:
        for day in dates:
            if stop_event and stop_event.is_set():
                emit("Stopped before remaining dates.")
                break
            local = local_dir_for(dest_root, day)
            os.makedirs(local, exist_ok=True)
            cmd = build_command(day, dest_root, opts)
            emit(f"=== Downloading files for date: {day} ===")
            emit(f"$ {format_command(cmd)}")
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                        start_new_session=os.name == "posix")
            except FileNotFoundError:
                emit(f"ERROR: could not find '{opts.bbftp}'. Is the bbftp client installed and on your PATH?")
                results.append(DateResult(day, None, local))
                break

            watcher = None
            if stop_event:
                def _watch(p=proc):
                    while p.poll() is None:
                        if stop_event.wait(0.5):
                            _kill(p)
                            return
                watcher = threading.Thread(target=_watch, daemon=True)
                watcher.start()

            assert proc.stdout is not None
            for line in proc.stdout:
                emit(line.rstrip("\n"))
            proc.wait()
            if watcher:
                watcher.join(timeout=1)

            files, total = _list_files(local)
            result = DateResult(day, proc.returncode, local, files, total)
            results.append(result)
            if stop_event and stop_event.is_set():
                emit(f"Download for date {day} stopped.")
            elif proc.returncode != 0:
                emit(f"Error downloading files for date {day} (bbftp exit code {proc.returncode})")
            elif not files:
                emit(f"WARNING: bbftp finished but no files landed in {local}. Check the elog that the target "
                     "was observed and the files are named correctly. If so, the data may not be archived yet.")
            else:
                emit(f"Download for date {day} successful: {len(files)} files, {human_size(total)}")
    finally:
        if log_fh:
            log_fh.close()
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dates", nargs="+", required=True, help="YYYYMMDD dates or YYYYMMDD-YYYYMMDD ranges")
    p.add_argument("--dest", required=True, help="local folder; each date gets its own subfolder")
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT)
    p.add_argument("--prefixes", default=DEFAULT_PREFIXES, help="file-name prefix letters (default TUGHJ)")
    p.add_argument("--bbftp", default="bbftp", help="path to the bbftp executable")
    p.add_argument("--no-ssh-batch", action="store_true", help="drop -S")
    p.add_argument("--quiet", action="store_true", help="drop -V")
    p.add_argument("--dry-run", action="store_true", help="print the commands without running them")
    args = p.parse_args(argv)

    try:
        dates = parse_dates(" ".join(args.dates))
        opts = DownloadOptions(user=args.user, server=args.server, remote_root=args.remote_root,
                               prefixes=normalize_prefixes(args.prefixes), bbftp=args.bbftp,
                               verbose=not args.quiet, ssh_batch=not args.no_ssh_batch)
    except ValueError as e:
        p.error(str(e))

    if args.dry_run:
        for day in dates:
            print(format_command(build_command(day, args.dest, opts)))
        return 0
    results = run_downloads(dates, args.dest, opts)
    return 0 if results and all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
