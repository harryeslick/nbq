from __future__ import annotations

import os
import signal
import time
from pathlib import Path
from typing import Optional

from .exec import launch_papermill, prepare_run, update_latest_symlink, write_status_json
from .ps import acquire_lock, kill_with_grace, release_lock
from .state import State, get_or_create_session, load_state, save_state
from .utils import iso_now

DEFAULT_KERNEL = os.environ.get("NBQ_DEFAULT_KERNEL", "python3")

def _pop_next_item(st: State) -> Optional[dict]:
    if not st.queue:
        return None
    return st.queue.pop(0)

def _finalize_current_append_history(item: dict, error: Optional[str] = None) -> dict:
    item["ended_at"] = item.get("ended_at") or iso_now()
    if error and not item.get("error"):
        item["error"] = error
    return item

def run_worker(timeout: Optional[int] = None, watch: bool = False, once: bool = False, poll_interval: float = 1.0) -> int:
    """
    Process queued items for the active or a new session.
    - timeout: per-cell execution timeout forwarded to papermill (None = no timeout)
    - watch: keep running and pick up newly added items
    - once: process a single item (if any) and exit
    Returns 0 on normal exit.
    """
    session = get_or_create_session()

    # Install signal handlers so killing the worker stops children and clears the queue
    def _handle_terminate(_signum, _frame):  # type: ignore[unused-argument]
        try:
            st = load_state(session)
            cur = st.current or {}
            pgid = cur.get("pgid")
            pid = cur.get("pid")
            if pgid is None and pid is not None:
                try:
                    pgid = os.getpgid(int(pid))
                except (ProcessLookupError, PermissionError, OSError):
                    pgid = None
            if pgid is not None:
                try:
                    kill_with_grace(int(pgid), grace_seconds=2.0)
                except OSError:
                    pass
                # Mark as canceled and finalize best-effort
                cur["status"] = "canceled"
                cur["error"] = cur.get("error") or "worker terminated"
                cur["ended_at"] = iso_now()
                st.current = cur
                try:
                    run_dir = Path(cur["run_dir"]) if cur.get("run_dir") else None
                    if run_dir:
                        write_status_json(run_dir, success=False, returncode=-1, error=cur["error"])
                except OSError:
                    pass
            # Empty the queue regardless
            st.queue = []
            save_state(session, st)
        finally:
            release_lock(session)
            os._exit(0)

    signal.signal(signal.SIGTERM, _handle_terminate)
    signal.signal(signal.SIGINT, _handle_terminate)

    if not acquire_lock(session):
        # Another worker is active; exit gracefully
        return 0

    exit_requested = False
    try:
        while not exit_requested:
            st = load_state(session)

            if st.stop_requested:
                # Graceful stop requested
                break

            item = _pop_next_item(st)
            if item is None:
                save_state(session, st)
                if once:
                    break
                if not watch:
                    break
                time.sleep(poll_interval)
                continue

            # Start processing this item
            item["status"] = "running"
            item["started_at"] = iso_now()

            try:
                # Create a new run directly under the session root
                run = prepare_run(Path(item["queue_path"]), session.root)
                item["run_dir"] = str(run.run_dir)
                st.current = item
                save_state(session, st)

                proc = launch_papermill(
                    input_ipynb=run.input_ipynb,
                    executed_ipynb=run.executed_ipynb,
                    kernel=DEFAULT_KERNEL,
                    timeout=timeout,
                    log_path=run.log_path,
                )
                item["pid"] = proc.pid
                try:
                    item["pgid"] = os.getpgid(proc.pid)
                except (ProcessLookupError, PermissionError, OSError):
                    item["pgid"] = None

                st.current = item
                save_state(session, st)

                returncode = proc.wait()
                # Reload state to check if a kill/abort marked it canceled
                st_after = load_state(session)
                canceled_by_user = bool(st_after.current and st_after.current.get("status") == "canceled")

                status_val = "canceled" if canceled_by_user else ("done" if returncode == 0 else "failed")
                item["status"] = status_val
                item["success"] = (returncode == 0) and not canceled_by_user
                item["returncode"] = int(returncode)
                item["ended_at"] = iso_now()
                if canceled_by_user:
                    item["error"] = item.get("error") or "killed by user"

                write_status_json(run.run_dir, success=bool(item["success"]), returncode=int(returncode), error=item.get("error"))
                update_latest_symlink(session.root, run.run_dir)

            except (OSError, RuntimeError, ValueError) as e:
                # Failure before or during launch; best-effort metadata
                item["status"] = "failed"
                item["success"] = False
                item["returncode"] = -1
                item["error"] = str(e)
                item["ended_at"] = iso_now()
                try:
                    # Try to write status.json in run_dir if available
                    run_dir = Path(item["run_dir"]) if item.get("run_dir") else None
                    if run_dir:
                        write_status_json(run_dir, success=False, returncode=-1, error=str(e))
                except OSError:
                    pass
            finally:
                # Append to history and clear current
                st_final = load_state(session)
                st_final.history.append(_finalize_current_append_history(item))
                st_final.current = None
                save_state(session, st_final)

                if once:
                    exit_requested = True

    finally:
        release_lock(session)
    return 0
