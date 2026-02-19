"""Capture protest ANSI output for documentation examples."""

import os
import subprocess
import sys

cmd = sys.argv[1:]
env = {**os.environ, "FORCE_COLOR": "1"}
proc = subprocess.run(cmd, capture_output=True, env=env)
raw = proc.stdout + proc.stderr

# Drop the "Full output:" log-path line (not useful in docs)
lines = raw.split(b"\n")
lines = [l for l in lines if b"Full output:" not in l]

# Strip trailing empty lines, add final newline
while lines and not lines[-1].strip():
    lines.pop()
sys.stdout.buffer.write(b"\n".join(lines) + b"\n")
