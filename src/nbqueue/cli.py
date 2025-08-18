from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .ps import kill_with_grace
from .state import (
    QueueItem,
    Session,
    active_session,
    append_queue,
    get_or_create_session,
    latest_session,
    load_state,
    read_lock_pid,
    save_state,
)
from .state import (
    clear_queue as clear_queue_state,
)
from .utils import elapsed_since, snapshot_source_to
from .worker import run_worker

app = typer.Typer(no_args_is_help=True)
console = Console()

# ASCII banner for nbqueue (barbequeue pun)
NBQ_BANNER = r"""
               ____
    _   _ ___ / __ \                       
 | \ | | __ )| |  | |_   _  ___ _   _  ___ 
 |  \| |  _ \| |  | | | | |/ _ \ | | |/ _ \
 | |\  | |_) | |__| | |_| |  __/ |_| |  __/
 |_| \_|____(_)___\_\\__,_|\___|\__,_|\___|

                ( ( (      ) ) )      barbequeue vibes
                 ) ) )    ( ( (       one hot run at a time
             .-~~~~~~~~~~~~~~~~-.   
            /  queue it and grill  \ 
            \______________________/ 
"""


def _print_banner(with_version: bool = True) -> None:
    try:
        console.print(NBQ_BANNER, style="bold red")
        if with_version:
            console.print(f"nbq v{__version__}", style="bold yellow")
    except (OSError, RuntimeError):
        pass


def _session_for_reporting() -> Optional[Session]:
    return active_session() or latest_session()

def _ensure_worker_running() -> None:
    sess = active_session()
    if sess:
        return
    # Launch background worker: nbq run --watch
    try:
        subprocess.Popen(
            [sys.executable, "-m", "nbqueue.cli", "run", "--watch"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        # Best-effort; surface no exception to keep add working
        pass

@app.command("add")
def cmd_add(
    paths: List[Path] = typer.Argument(..., help="Paths to .ipynb or .py files"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Optional tag for tracking"),
    start: bool = typer.Option(False, "--start", help="Ensure a worker is running"),
) -> None:
    """
    Enqueue notebooks/scripts into the current session queue.
    .ipynb are cleared of outputs before snapshot; .py are copied as-is.
    """
    session = get_or_create_session()
    added = 0
    for p in paths:
        p = p.expanduser()
        if not p.exists():
            console.print(f"[yellow]Skipping missing path:[/yellow] {p}")
            continue
        snap = snapshot_source_to(session.queue_dir, p, tag)
        item = QueueItem.make(original_path=p, queue_path=snap, tag=tag)
        append_queue(session, item)
        added += 1
        console.print(f"[green]Enqueued[/green] {p.name} -> {snap.name}")
    if start:
        _ensure_worker_running()
    if added == 0:
        raise typer.Exit(code=1)

@app.command("status")
def cmd_status(json_out: bool = typer.Option(False, "--json", help="Output machine-readable JSON")) -> None:
    """
    Show current session status (running and queued items).
    """
    sess = _session_for_reporting()
    if not sess:
        console.print("[dim]No sessions found.[/dim]")
        raise typer.Exit(code=0)

    st = load_state(sess)
    worker_pid = read_lock_pid(sess)
    if json_out:
        console.print_json(
            json.dumps({"version": __version__, "session": str(sess.root), "worker_pid": worker_pid, **st.to_dict()})
        )
        return

    # Pretty banner for human-readable status
    _print_banner(with_version=True)

    subtitle = f"worker pid: {worker_pid}" if worker_pid else "no worker running"
    table = Table(title=f"nbq v{__version__} status – session {sess.root.name}", caption=subtitle, show_lines=False)
    table.add_column("ID", no_wrap=True)
    table.add_column("Notebook", no_wrap=True)
    table.add_column("Tag", no_wrap=True)
    table.add_column("Status", no_wrap=True)
    table.add_column("Elapsed", no_wrap=True)
    table.add_column("Result", no_wrap=True)

    # Current running
    if st.current:
        cur = st.current
        nb_name = Path(cur.get("queue_path", "")).name or "-"
        elapsed = elapsed_since(cur.get("started_at") or cur.get("added_at") or "")
        result = ""
        table.add_row(cur.get("id", "-"), nb_name, str(cur.get("tag") or ""), cur.get("status", "-"), elapsed, result)

    # Queued items
    for qi in st.queue:
        nb_name = Path(qi.get("queue_path", "")).name or "-"
        elapsed = elapsed_since(qi.get("added_at") or "")
        table.add_row(qi.get("id", "-"), nb_name, str(qi.get("tag") or ""), qi.get("status", "queued"), elapsed, "")

    # If nothing to show
    if not st.current and not st.queue:
        table.add_row("-", "-", "-", "-", "-", "-")
    console.print(table)

@app.command("run")
def cmd_run(
    timeout: Optional[int] = typer.Option(None, "--timeout", help="Per-cell timeout in seconds"),
    watch: bool = typer.Option(False, "--watch", help="Keep worker alive to pick up new items"),
    once: bool = typer.Option(False, "--once", help="Process a single item (if any) and exit"),
) -> None:
    """
    Run worker loop to process queued items.
    """
    # If a worker is already running, do nothing and inform the user.
    sess_running = active_session()
    if sess_running:
        pid = read_lock_pid(sess_running)
        if pid:
            console.print(f"[yellow]A worker is already running (pid {pid}). No action taken.[/yellow]")
            raise typer.Exit(code=0)
    code = run_worker(timeout=timeout, watch=watch, once=once)
    raise typer.Exit(code=code)

@app.command("clear")
def cmd_clear(yes: bool = typer.Option(..., "--yes", help="Confirm clearing the pending queue")) -> None:
    """
    Clear pending queue (does not touch current run or history).
    """
    if not yes:
        console.print("[yellow]Refusing to clear queue without --yes.[/yellow]")
        raise typer.Exit(code=1)
    sess = _session_for_reporting()
    if not sess:
        console.print("[dim]No sessions found.[/dim]")
        raise typer.Exit(code=0)
    clear_queue_state(sess)
    console.print("[green]Cleared pending queue.[/green]")

@app.command("cancel")
def cmd_cancel() -> None:
    """
    Request a graceful stop; worker exits after finishing current notebook.
    """
    sess = _session_for_reporting()
    if not sess:
        console.print("[dim]No sessions found.[/dim]")
        raise typer.Exit(code=0)
    st = load_state(sess)
    st.stop_requested = True
    save_state(sess, st)
    console.print("[yellow]Stop requested. Worker will exit after the current run.[/yellow]")

@app.command("kill")
def cmd_kill(grace: float = typer.Option(5.0, "--grace", help="Seconds to wait before SIGKILL")) -> None:
    """
    Send SIGTERM to the running notebook's process group, then SIGKILL after grace; marks run as canceled.
    """
    sess = active_session()
    if not sess:
        console.print("[dim]No active worker.[/dim]")
        raise typer.Exit(code=0)
    st = load_state(sess)
    cur = st.current or {}
    pgid = cur.get("pgid")
    pid = cur.get("pid")
    if pgid is None and pid is not None:
        try:
            pgid = os.getpgid(int(pid))
        except (ProcessLookupError, PermissionError, OSError):
            pgid = None
    if pgid is None:
        console.print("[yellow]No running process to kill.[/yellow]")
        raise typer.Exit(code=0)

    try:
        kill_with_grace(int(pgid), grace_seconds=float(grace))
    finally:
        # Mark as canceled; worker will observe this on wait()
        cur["status"] = "canceled"
        cur["error"] = cur.get("error") or "killed by user"
        st.current = cur
    # Also clear any pending items to align with expected behavior
    st.queue = []
    save_state(sess, st)
    console.print("[red]Kill signal sent. Marked current run as canceled and cleared pending queue.[/red]")

@app.command("abort")
def cmd_abort(
    grace: float = typer.Option(5.0, "--grace", help="Seconds to wait before SIGKILL"),
    no_clear_queue: bool = typer.Option(False, "--no-clear-queue", help="Do not clear pending queue"),
) -> None:
    """
    Kill current run (if any), mark canceled, clear queue by default, and set stop flag.
    """
    sess = _session_for_reporting()
    if not sess:
        console.print("[dim]No sessions found.[/dim]")
        raise typer.Exit(code=0)

    st = load_state(sess)
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
            kill_with_grace(int(pgid), grace_seconds=float(grace))
        except OSError:
            pass
        cur["status"] = "canceled"
        cur["error"] = cur.get("error") or "killed by user"
        st.current = cur

    if not no_clear_queue:
        st.queue = []

    st.stop_requested = True
    save_state(sess, st)
    console.print("[red]Abort requested.[/red] Current killed (if running), queue cleared, worker will stop.")

def main() -> None:
    # If invoked without subcommand, print banner + version before help
    try:
        if len(sys.argv) == 1:
            _print_banner(with_version=True)
    except (OSError, RuntimeError):
        pass
    app()

if __name__ == "__main__":
    main()
