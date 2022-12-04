# Create thumbnails of image files.

from datetime import datetime
import argparse
import os
import os.path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(
    prog="Memory",
    description="Create thumbnails from image files",
)
parser.add_argument(
    "-s",
    "--source",
    dest="source",
    help="Source directory path to find files",
)
parser.add_argument(
    "-d",
    "--dest",
    dest="dest",
    help="Destination directory path to put thumbnails",
)
parser.add_argument(
    "-w",
    "--width",
    dest="w",
    type=int,
    default=200,
    help="Width of the thumbnails",
)
args = parser.parse_args()

if not os.path.isdir(args.source):
    print(f"Failed to locate a directory at {args.source}!", file=sys.stderr)
    print(f"You may have entered a wrong value for --source", file=sys.stderr)
    sys.exit()

if not os.path.isdir(args.dest):
    print(f"Failed to locate a directory at {args.dest}!", file=sys.stderr)
    print(f"You may have entered a wrong value for --dest", file=sys.stderr)
    sys.exit()

files = os.listdir(args.source)  # Get initial list of files and directories
files = (os.path.join(args.source, f) for f in files)  # Get full paths
files = (f for f in files if os.path.isfile(f))  # Filter out directories
# Filter out non image files
files = (f for f in files if os.path.splitext(f)[1].lower() in (".jpg", ".cr2"))
files = list(files)  # Run generators and get a list

err_count = 0

for i, f in enumerate(files, start=1):
    print(f"[{i}/{len(files)}] Processing {f}")

    base, ext = os.path.splitext(os.path.basename(f))
    thumb_path = os.path.join(args.dest, f"{base}_thumb.JPG")
    jpg_path = os.path.join(args.source, f"{base}.JPG")
    tmp_jpg_path = False

    print(f"\t{thumb_path=}")
    print(f"\t{jpg_path=}")

    # A thumb may have already be created if the current file has a duplicate in
    # a different file format (say, cr2 or jpg) and that duplicate was processed
    # eariler by the script.
    if os.path.isfile(thumb_path):
        print("\tThumbnail already exists. Skipping.")
        continue

    # If there does not exist any jpg file to create a thumbnail from, create
    # it.
    if not os.path.isfile(jpg_path):
        jpg_path = tempfile.mktemp(suffix=".jpg")
        print(f"\tJpg file does not exist. Creating one at {jpg_path}")
        p = subprocess.run(
            ["darktable-cli", f, jpg_path],
            capture_output=True,
            shell=False,
        )
        try:
            p.check_returncode()
        except subprocess.CalledProcessError:
            err_count += 1
            print("\tEncountered error. Writing log and skipping.", file=sys.stderr)
            with open("memory_log.txt", "at") as log:
                now = datetime.now()
                print(f"[{now.isoformat()}] Failed to create jpg from {f}", file=log)
                print("stdout:", file=log)
                print(p.stdout.decode(), file=log)
                print("stderr:", file=log)
                print(p.stderr.decode(), file=log)
                print("exiftool:", file=log)
                p = subprocess.run(
                    ["exiftool", f],
                    capture_output=True,
                    shell=False,
                )
                print(p.stdout.decode(), file=log)
                print("-" * 80, file=log)
            continue

        tmp_jpg_path = True

    subprocess.run(
        ["convert", "-thumbnail", str(args.w), jpg_path, thumb_path],
        check=True,
        shell=False,
    )

    # Delete temp files.
    if tmp_jpg_path:
        os.remove(jpg_path)

if err_count != 0:
    print(f"Encountered {err_count} errors!", file=sys.stderr)
