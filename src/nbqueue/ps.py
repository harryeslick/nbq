from __future__ import annotations

import os
import signal
import time
from typing import Optional

from .state import Session, read_lock_pid, is_pid_alive

def acquire_lock(session: Session) -> bool:
    """
    Acquire single-worker lock. Returns True if acquired, False if another live worker holds it.
    Removes stale locks automatically.
    """
    lp = session.lock_path
    lp.parent.mkdir(parents=True, exist_ok=True)
    pid = read_lock_pid(session)
    if pid and is_pid_alive(pid):
        return False
    # stale or missing -> write our pid
    try:
        lp.write_text(str(os.getpid()), encoding="utf-8")
        return True
    except Exception:
        return False

def release_lock(session: Session) -> None:
    """
    Release the lock if it belongs to this process.
    """
    try:
        pid = read_lock_pid(session)
        if pid == os.getpid() and session.lock_path.exists():
            session.lock_path.unlink(missing_ok=True)
    except Exception:
        pass

def get_pgid(pid: int) -> Optional[int]:
    try:
        return os.getpgid(pid)
    except Exception:
        return None

def send_signal_to_pgid(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except AttributeError:
        # Fallback if killpg is unavailable
        os.kill(-pgid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Best-effort
        pass

def kill_with_grace(pgid: int, grace_seconds: float = 5.0) -> None:
    """
    SIGTERM the process group, wait up to grace_seconds, then SIGKILL.
    """
    send_signal_to_pgid(pgid, signal.SIGTERM)
    waited = 0.0
    step = 0.1
    while waited < grace_seconds:
        time.sleep(step)
        waited += step
        # No portable way to check if group is empty; we just try KILL after grace.
        # Early exit possible if all procs have died, but we keep it simple.
    send_signal_to_pgid(pgid, signal.SIGKILL)
