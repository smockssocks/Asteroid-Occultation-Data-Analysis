import os
import stat
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "download"))
import bbftp_download as bd  # noqa: E402


def test_parse_dates_lists_and_ranges():
    assert bd.parse_dates("20250420, 20250421") == ["20250420", "20250421"]
    assert bd.parse_dates("20250430 - 20250502\n20250420") == ["20250430", "20250501", "20250502", "20250420"]
    assert bd.parse_dates("20250420 20250420") == ["20250420"]
    assert bd.parse_dates("  ") == []


@pytest.mark.parametrize("bad", ["2025042", "20251340", "20250425-20250420", "april"])
def test_parse_dates_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        bd.parse_dates(bad)


def test_build_command_matches_original_script():
    cmd = bd.build_command("20250420", "/data", bd.DownloadOptions())
    assert cmd == ["bbftp", "-V", "-S", "-u", "bbftp", "-e",
                   "mget /veritas/DATAQ/d20250420/20250420-[TUGHJ]* /data/20250420/",
                   "gamma1.astro.ucla.edu"]


def test_prefixes_are_normalized():
    assert bd.normalize_prefixes("t,u g") == "TUG"
    with pytest.raises(ValueError):
        bd.normalize_prefixes("")


def _fake_bbftp(tmp_path, body):
    script = tmp_path / "fake_bbftp"
    script.write_text("#!/bin/sh\n" + body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_run_downloads_success_and_empty(tmp_path):
    # Writes a file into the destination only for 20250420 (the last argument after -e is the mget string).
    fake = _fake_bbftp(tmp_path, 'dest=$(echo "$6" | awk \'{print $3}\')\n'
                                 'case "$dest" in *20250420*) echo data > "${dest}20250420-T1.WDQ";; esac\n'
                                 'echo transferred\n')
    out = tmp_path / "out"
    lines = []
    results = bd.run_downloads(["20250420", "20250421"], str(out), bd.DownloadOptions(bbftp=fake), log=lines.append)
    assert [r.ok for r in results] == [True, False]
    assert results[0].files == ["20250420-T1.WDQ"]
    assert any("WARNING" in l for l in lines)
    assert "transferred" in (out / "bbftp_log.txt").read_text()


def test_run_downloads_reports_failure_and_missing_binary(tmp_path):
    fake = _fake_bbftp(tmp_path, "echo boom; exit 3\n")
    results = bd.run_downloads(["20250420"], str(tmp_path), bd.DownloadOptions(bbftp=fake, log_file=None), log=lambda _: None)
    assert results[0].returncode == 3
    results = bd.run_downloads(["20250420", "20250421"], str(tmp_path),
                               bd.DownloadOptions(bbftp=str(tmp_path / "nope"), log_file=None), log=lambda _: None)
    assert len(results) == 1 and results[0].returncode is None


def test_stop_event_kills_transfer(tmp_path):
    fake = _fake_bbftp(tmp_path, "sleep 30\n")
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    results = bd.run_downloads(["20250420", "20250421"], str(tmp_path), bd.DownloadOptions(bbftp=fake, log_file=None),
                               log=lambda _: None, stop_event=stop)
    assert len(results) == 1 and results[0].returncode != 0


def test_password_switches_to_interactive_ssh_mode():
    cmd = bd.build_command("20250420", "/data", bd.DownloadOptions(password="secret"))
    assert "-s" in cmd and "-S" not in cmd
    assert "secret" not in " ".join(cmd)
    assert "secret" not in repr(bd.DownloadOptions(password="secret"))


def test_password_reaches_ssh_through_askpass_only(tmp_path):
    # The fake bbftp calls the askpass helper the way ssh would.
    fake = _fake_bbftp(tmp_path, 'echo "got: $("$SSH_ASKPASS")"\n')
    out = tmp_path / "out"
    lines = []
    bd.run_downloads(["20250420"], str(out), bd.DownloadOptions(bbftp=fake, password="s3cret"), log=lines.append)
    assert "got: s3cret" in lines
    for path in out.rglob("*"):
        if path.is_file() and path.name != "bbftp_log.txt":
            assert "s3cret" not in path.read_text()
