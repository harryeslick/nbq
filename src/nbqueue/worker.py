from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from .exec import prepare_run, launch_papermill, write_status_json, update_latest_symlink
from .ps import acquire_lock, release_lock
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

    if not acquire_lock(session):
        # Another worker is active; exit gracefully
        return 0

    try:
        while True:
            st = load_state(session)

            if st.stop_requested:
                # Graceful stop requested
                return 0

            item = _pop_next_item(st)
            if item is None:
                save_state(session, st)
                if once:
                    return 0
                if not watch:
                    return 0
                time.sleep(poll_interval)
                continue

            # Start processing this item
            item["status"] = "running"
            item["started_at"] = iso_now()

            try:
                run = prepare_run(Path(item["queue_path"]), session.output_dir)
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
                except Exception:
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

            except Exception as e:
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
                except Exception:
                    pass
            finally:
                # Append to history and clear current
                st_final = load_state(session)
                st_final.history.append(_finalize_current_append_history(item))
                st_final.current = None
                save_state(session, st_final)

                if once:
                    return 0

    finally:
        release_lock(session)
