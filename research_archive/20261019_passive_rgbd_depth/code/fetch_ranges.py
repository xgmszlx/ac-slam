"""Bounded HTTP Range download, shared output via pwrite; no dataset alteration."""
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import requests

url, output, size_s = sys.argv[1:]
output = Path(output)
size = int(size_s)
chunk = 16 * 1024 * 1024
started = time.monotonic()
fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o644)
os.ftruncate(fd, size)
events = []

def fetch(start):
    end = min(size, start + chunk) - 1
    for attempt in range(2):
        session = requests.Session()
        session.trust_env = True
        try:
            with session.get(url, headers={"Range": f"bytes={start}-{end}"},
                             stream=True, timeout=(20, 120)) as response:
                response.raise_for_status()
                expected = f"bytes {start}-{end}/{size}"
                if response.status_code != 206 or response.headers.get("Content-Range") != expected:
                    raise ValueError(f"Invalid range response: {dict(response.headers)}")
                pos = start
                for data in response.iter_content(262144):
                    if pos + len(data) > end + 1:
                        raise ValueError("range overflow")
                    written = os.pwrite(fd, data, pos)
                    if written != len(data):
                        raise IOError("short pwrite")
                    pos += written
                if pos != end + 1:
                    raise ValueError("short range")
                return {"start": start, "end": end, "attempt": attempt, "elapsed": time.monotonic()-started}
        except Exception as error:
            print(json.dumps({"start": start, "attempt": attempt, "error": str(error)}), flush=True)
            if attempt == 1:
                raise
        finally:
            session.close()

try:
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        for event in pool.map(fetch, range(0, size, chunk)):
            events.append(event)
            print(json.dumps(event), flush=True)
finally:
    os.close(fd)
    output.with_suffix(output.suffix + ".ranges.json").write_text(json.dumps(events, indent=2))
print("sha256", hashlib.file_digest(output.open("rb"), "sha256").hexdigest(), flush=True)
