import time
import os

_LOG_FILE = "/tmp/profile_rotation.log"

def log(msg: str):
    pid = os.getpid()
    with open(_LOG_FILE, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] pid={pid} {msg}\n")
