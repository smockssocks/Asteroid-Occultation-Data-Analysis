# Occultation data downloader

A small GUI around the bbftp command used to pull VERITAS occultation
(`.WDQ`) data from the UCLA archive. For each date it makes a folder and runs:

```
bbftp -V -S -u bbftp -e "mget /veritas/DATAQ/d<date>/<date>-[TUGHJ]* <dest>/<date>/" gamma1.astro.ucla.edu
```

## Before you start

1. **Set up your machine for the UCLA archive.** Install the bbftp client and
   the SSH key the archive expects. Without this, no download will work. The
   app has no password box because `-S` logs in with that key.
2. **Check the [elog](http://veritash.sao.arizona.edu:8081/)** for each date.
   Make sure the target was observed and the files are named correctly.
3. If the target was observed, bbftp works, it isn't the weekend, and you
   still get nothing, the ECM data probably hasn't been archived yet. Email
   Bill Hanlon (and be patient with the day crew).

## Running it

Needs Python 3.9+ with Tkinter (on Ubuntu/WSL: `sudo apt install python3-tk`;
the python.org installers for macOS/Windows include it). bbftp itself is a
Unix tool, so on Windows run this inside WSL.

```
cd download
python3 download_gui.py
```

1. Check the connection settings (the defaults match the standard script).
2. Enter dates as `YYYYMMDD`, separated by commas, spaces or new lines.
   Ranges like `20250420-20250425` work too.
3. Pick the file prefixes (all of `TUGHJ` by default) and a folder to save to.
4. Press **Preview commands** to see exactly what will run, then **Start download**.

Output shows up live in the window and is also appended to
`bbftp_log.txt` in the save folder. When it finishes you get a per-date
summary of how many files arrived and how big they are. **Stop** kills the
running transfer. Your settings are remembered in `~/.ao_download_gui.json`.

## No display? (e.g. over SSH on a server)

The same logic runs from the command line:

```
python3 bbftp_download.py --dates 20250420 20250421 --dest ~/AO/data
python3 bbftp_download.py --dates 20250420-20250425 --dest ~/AO/data --dry-run   # just print commands
```

Run `python3 bbftp_download.py -h` for every option.
