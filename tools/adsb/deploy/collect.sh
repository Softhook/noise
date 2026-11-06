#!/bin/sh
# Copy the logs from the Pi to this laptop and check every copy against its SHA-256 checksum.
# Runs on the laptop; usually as `make pi-collect`.
#
#   sh deploy/collect.sh [--all] PI [FOLDER]
#
# PI is anything ssh accepts, such as adsb-pi.local or pi@10.42.0.1. FOLDER defaults to
# data/collected. Files that may still be written to (the newest data file and today's health log)
# are left for the next visit, so every copied file is final and its checksum never changes. --all copies those too: use it only after `sudo systemctl stop adsb-logger`, at the end.
#
# Nothing on the Pi is changed or deleted. A file already collected is never overwritten: if the
# Pi's copy differs from it, that's reported. FOLDER/SHA256SUMS lists every file collected so far.
set -eu

SSH=${SSH:-ssh}
LOG_DIR=${LOG_DIR:-/var/lib/adsb-logger}  # On the Pi

ALL=0
[ "${1:-}" != "--all" ] || { ALL=1; shift; }
[ $# -ge 1 ] || { echo "usage: sh deploy/collect.sh [--all] PI [FOLDER]" >&2; exit 2; }
PI=$1
DEST=${2:-data/collected}

if command -v sha256sum >/dev/null; then sha256() { sha256sum "$@"; }
else sha256() { shasum -a 256 "$@"; }
fi

mkdir -p "$DEST"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# On the Pi: list the finished files with their checksums
echo "==> Checksumming the logs on $PI"
$SSH "$PI" sh -s -- "$LOG_DIR" "$ALL" > "$work/remote.sums" <<'EOF'
set -eu
cd "$1"
mountpoint -q . || echo "WARNING: $1 isn't a mounted disk; is the SSD plugged in?" >&2
newest=$(ls -t adsb/*.jsonl.gz 2>/dev/null | head -n 1)
today=health/$(date -u +%Y-%m-%d).jsonl
for f in adsb/*.jsonl.gz health/*.jsonl; do
    [ -f "$f" ] || continue
    if [ "$2" -eq 0 ]; then
        case "$f" in "$newest"|"$today") continue ;; esac
    fi
    echo "$f"
done | xargs -r sha256sum
EOF

count=$(wc -l < "$work/remote.sums" | tr -d ' ')
[ "$count" -gt 0 ] || { echo "No finished log files on $PI yet."; exit 0; }
awk '{print $2}' "$work/remote.sums" > "$work/files"

echo "==> Copying new files to $DEST"
# --ignore-existing: never overwrite a file collected earlier; a changed one is caught below
rsync -a --ignore-existing --files-from="$work/files" -e "$SSH" "$PI:$LOG_DIR/" "$DEST/"

echo "==> Checking $count files"
if (cd "$DEST" && sha256 -c --quiet "$work/remote.sums") > "$work/check" 2>&1; then
    # Add them to the folder's list of every file collected
    touch "$DEST/SHA256SUMS"
    sort -u -k 2 "$DEST/SHA256SUMS" "$work/remote.sums" > "$work/all.sums"
    mv "$work/all.sums" "$DEST/SHA256SUMS"
    size=$(du -sh "$DEST" | cut -f 1)
    echo "OK: all $count files match the Pi. $DEST now holds $(wc -l < "$DEST/SHA256SUMS" | tr -d ' ') files, $size."
    echo "Keep a second copy off site. Nothing was deleted from the Pi."
else
    cat "$work/check"
    echo "FAILED: the files above differ from the Pi's. Nothing was overwritten or deleted. Run this" >&2
    echo "again; if they still differ, note it in the survey log before changing anything." >&2
    exit 1
fi
