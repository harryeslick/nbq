from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import jupytext  # type: ignore
import nbformat  # type: ignore

from .utils import atomic_write_json, ensure_dir, iso_now, run_id


@dataclass
class PreparedRun:
    run_dir: Path
    source_copy: Path        # path to copied source.ext
    input_ipynb: Path        # notebook to execute
    executed_ipynb: Path     # output executed notebook path
    log_path: Path           # stdout/stderr stream

def prepare_run(queued_file: Path, session_root_dir: Path) -> PreparedRun:
    """
    Create a new run directory, copy queued file to 'source.ext',
    and (if needed) convert .py to .ipynb for execution.
    """
    rid = run_id()
    # Place runs directly under the session root for a flatter structure
    run_dir = session_root_dir / rid
    ensure_dir(run_dir)

    queued_file = queued_file.resolve()
    ext = queued_file.suffix.lower()
    source_copy = run_dir / f"source{ext}"
    shutil.copy2(queued_file, source_copy)

    input_ipynb = run_dir / "input.ipynb"
    executed_ipynb = run_dir / "executed.ipynb"
    if ext == ".ipynb":
        input_ipynb = source_copy
    else:
        nb = jupytext.read(str(source_copy))  # auto-detect percent or other formats
        nbformat.write(nb, str(input_ipynb))

    log_path = run_dir / "run.log"
    return PreparedRun(
        run_dir=run_dir,
        source_copy=source_copy,
        input_ipynb=input_ipynb,
        executed_ipynb=executed_ipynb,
        log_path=log_path,
    )

def launch_papermill(input_ipynb: Path, executed_ipynb: Path, kernel: str, timeout: Optional[int], log_path: Path) -> subprocess.Popen:
    """
    Launch papermill as a subprocess, streaming stdout/stderr to log_path.
    Returns the Popen handle. Uses start_new_session=True so child becomes a PGID leader.
    """
    args = [
        sys.executable, "-m", "papermill",
        str(input_ipynb),
        str(executed_ipynb),
        "--kernel", kernel,
    ]
    if timeout is not None:
        args += ["--execution-timeout", str(timeout)]

    log_f = open(log_path, "a", encoding="utf-8")
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    proc = subprocess.Popen(
        args,
        stdout=log_f,
        stderr=log_f,
        cwd=str(input_ipynb.parent),
        env=env,
        start_new_session=True,
    )
    return proc

def write_status_json(run_dir: Path, success: bool, returncode: int, error: Optional[str]) -> None:
    status = {
        "started_at": iso_now(),
        "ended_at": iso_now(),
        "success": bool(success),
        "returncode": int(returncode),
        "error": error,
    }
    atomic_write_json(run_dir / "status.json", status)

def update_latest_symlink(session_root: Path, run_dir: Path) -> None:
    link = session_root / "latest_run"
    try:
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(run_dir, target_is_directory=True)
    except OSError:
        pass
