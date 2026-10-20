# Occultation data downloader

A small GUI around the bbftp command used to pull VERITAS occultation
(`.WDQ`) data from the UCLA archive. For each date it makes a folder and runs:

```
bbftp -V -S -u bbftp -e "mget /veritas/DATAQ/d<date>/<date>-[TUGHJ]* <dest>/<date>/" gamma1.astro.ucla.edu
```

## Before you start

1. **Set up your machine for the UCLA archive.** Install the bbftp client and
   the SSH key the archive expects. Without this, no download will work.
   With a key, `-S` logs in without asking for anything. If your account uses
   a password instead, type it in the app's optional **Password** box (see
   [Logins and passwords](#logins-and-passwords)).
2. **Check the [elog](http://veritash.sao.arizona.edu:8081/)** for each date.
   Make sure the target was observed and the files are named correctly.
3. If the target was observed, bbftp works, it isn't the weekend, and you
   still get nothing, the ECM data probably hasn't been archived yet. Email
   Bill Hanlon (and be patient with the day crew).

## Using it from Windows

bbftp is a Linux program, so on Windows the app runs inside Ubuntu (WSL) and
its window shows up on your normal Windows desktop. This needs Windows 11, or
Windows 10 with a recent WSL (run `wsl --update` in PowerShell if the window
never appears).

One-time setup, in the **Ubuntu** app (the black terminal window):

```
sudo apt update
sudo apt install python3 python3-tk git
git clone https://github.com/smockssocks/Asteroid-Occultation-Data-Analysis.git
```

Install bbftp and your archive SSH key in Ubuntu too, as in step 1 above.

After that, open File Explorer, go to
`\\wsl$\Ubuntu\home\<your Ubuntu username>\Asteroid-Occultation-Data-Analysis\download`,
and double-click **Start Downloader (Windows).bat**. You can right-click it
and pick *Show more options → Send to → Desktop (create shortcut)* so it's one
click next time.

Prefer typing? In Ubuntu:

```
cd ~/Asteroid-Occultation-Data-Analysis/download
python3 download_gui.py
```

Tip: save data under your Ubuntu home (the default `~/AO/data`). Saving to a
Windows drive like `/mnt/c/...` works but is much slower.

## Running it on Linux or macOS

Needs Python 3.9+ with Tkinter (on Ubuntu: `sudo apt install python3-tk`;
the python.org installer for macOS includes it) and the bbftp client.

```
cd download
python3 download_gui.py
```

## Filling in the window

1. Check the connection settings (the defaults match the standard script).
2. Enter dates as `YYYYMMDD`, separated by commas, spaces or new lines.
   Ranges like `20250420-20250425` work too.
3. Pick the file prefixes (all of `TUGHJ` by default) and a folder to save to.
4. Press **Preview commands** to see exactly what will run, then **Start download**.

Output shows up live in the window and is also appended to
`bbftp_log.txt` in the save folder. When it finishes you get a per-date
summary of how many files arrived and how big they are. **Stop** kills the
running transfer. Your settings are remembered in `~/.ao_download_gui.json`
(never the password).

## Logins and passwords

Nothing about your login is stored in this repository, and nothing should be:
don't commit SSH keys, passwords or a filled-in settings file.

- **SSH key (normal):** leave the password box empty. bbftp runs with `-S` and
  ssh uses the key in `~/.ssh` on your machine.
- **Password:** type it in the password box. bbftp then runs with `-s`, and
  the password is passed to ssh through a throwaway helper while the download
  runs. It is not written to the settings file or the log, and it's forgotten
  when you close the app. From the command line, add `--ask-password`.

## No display? (e.g. over SSH on a server)

The same logic runs from the command line:

```
python3 bbftp_download.py --dates 20250420 20250421 --dest ~/AO/data
python3 bbftp_download.py --dates 20250420-20250425 --dest ~/AO/data --dry-run   # just print commands
```

Run `python3 bbftp_download.py -h` for every option.
