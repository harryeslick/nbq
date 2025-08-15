# nbqueue – Design and Implementation Plan (Standalone Package)

A single-worker queue for executing Jupyter notebooks (and Python “percent” notebooks via Jupytext) one at a time with a simple CLI. Supports tagging runs, live status, safe cancel/kill, and reliable artifact capture.

## Purpose

- Execute one notebook at a time (.ipynb or .py via Jupytext) with robust CLI controls.
- Provide durable state, resumability, logs, and artifact capture.

## Scope and platform

- Single worker only; enforced via `lock.pid` (no multi-worker).
- Target POSIX systems (macOS/Linux) for process group signaling (SIGTERM/SIGKILL). Windows support out of scope for now.

## Goals

- Single active run; remaining items queued FIFO.
- Robust CLI for add/status/run/clear/cancel/kill/abort.
- Works with .ipynb and .py (Jupytext) sources.
- Clear, durable state and logs; easy to resume after interruption.
- Minimal dependencies and simple install (console script).

## Non-goals

- Distributed workers or parallel execution.
- Rich scheduling (priorities, dependencies).
- Cloud backends or remote execution.

## User stories

- Enqueue notebooks to run, with an optional tag for tracking.
- See what’s running and what’s queued, with elapsed time and result.
- Run the queue; optionally watch for new items to arrive.
- Cancel the worker after the current run finishes.
- Kill the currently running notebook now.
- Abort everything (kill current, clear queue, stop worker).
- For .py files, convert to .ipynb using Jupytext.

## Directory layout

Default base directory (NBQ_HOME) is `./nbqueue` unless overridden via `NBQ_HOME`.

- `nbqueue/<session-id>/`
  - `queue/` – inbox of pending items (snapshotted copies from enqueue)
  - `output/` – per-run outputs; each run uses `output/<run-id>/...`
    - `source.ext` – the copied source used for execution
    - `executed.ipynb` – executed notebook
    - `run.log` – stdout/stderr stream
    - `status.json` – run result metadata
  - `logs/` – optional additional logs (e.g., symlink/tee of run logs)
  - `state.json` – queue, history, current, stop flags
  - `lock.pid` – single-worker enforcement
  - `latest_run -> output/<run-id>` – symlink to latest run (best-effort)

Notes:
- `<session-id>` can be a timestamp or ULID (e.g., `2025-08-15T07-10-03Z` or `01J...`).
- `<run-id>` can be monotonic timestamp/ULID; it is the source of filename uniqueness.

## CLI specification

### nbq add
```bash
nbq add [--tag TAG] [--start] PATH...
```
- Accepts relative or absolute paths.
- `--tag` attaches metadata and is also appended to the snapshotted filename in `queue/` (see Enqueue rules).
- `--start` ensures a worker is running (`nbq run --watch`) if none is active; idempotent if already running.

### nbq status
```bash
nbq status [--json]
```
- Shows: ID, Notebook (basename), Tag, Status, Elapsed, Result (success/returncode).
- Elapsed is since `started_at` for running and since `added_at` for queued.
- `--json` outputs machine-readable status.

### nbq run
```bash
nbq run [--timeout SECONDS] [--watch] [--once]
```
- Processes items one at a time; optional per-cell timeout forwarded to executor.
- `--watch` keeps the worker alive to pick up newly added items.
- `--once` processes a single item (if any) and exits.

### nbq clear
```bash
nbq clear --yes
```
- Clears pending queue (does not touch current run or history).

### nbq cancel
```bash
nbq cancel
```
- Requests a graceful stop; worker exits after finishing the current notebook.

### nbq kill
```bash
nbq kill [--grace SECONDS]
```
- Sends SIGTERM to the running notebook’s process group, then SIGKILL after grace; marks the run as canceled.

### nbq abort
```bash
nbq abort [--grace SECONDS] [--no-clear-queue]
```
- Kills current run (if any), marks it canceled, clears queue by default, and raises the stop flag.

## Behavior and data flow

### Session management
- If an active session exists (determined by a live `lock.pid` in `nbqueue/<session-id>`), reuse it.
- Otherwise, create a new session directory `nbqueue/<session-id>` with subdirectories and `state.json`.

### Enqueue
- Snapshot the input into `nbqueue/<session-id>/queue/`:
  - If `.py`: copy as `<stem>_<tag>.py` when `--tag` is provided; else keep original basename. Sanitize tag and preserve extension.
  - If `.ipynb`: copy as `<stem>_<tag>.ipynb` (if tagged), but first clear all output cells before saving to `queue/`.
- Create a `QueueItem` and append to `state.json.queue` (FIFO).
- Keep `original_path` in metadata; `queue_path` points to the snapshotted file in `queue/`.

### Run loop
- Acquire single-worker lock (`lock.pid`). If another worker is alive, exit.
- If a stop flag is present, exit gracefully.
- Pop next queued item; set `current.status=running`; set `started_at`; create a new `<run-id>`.

### Execute notebook
- Copy the queued file to `nbqueue/<session-id>/output/<run-id>/source.ext`.
- If `.py`: convert to a temp `.ipynb` using Jupytext (respecting cell markers) within the run directory.
- Execute with Papermill/NBClient, writing `executed.ipynb` in the run directory.
- Pass a default kernel (`--kernel python3`) to avoid missing kernelspec.
- Disable progress bars that write to pipes (avoid BrokenPipe).
- Stream stdout/stderr to `output/<run-id>/run.log`.
- On completion, write `status.json` in the run directory with `success`, `returncode`, timings, and error (if any). Update `latest_run` symlink.

### Finalize
- If `kill` was requested, mark `status=canceled`; otherwise `done` or `failed`.
- Append the item to `history`; clear `current`; persist `state.json`.
- Do not write executed files back to `queue/` (queue remains inputs only).

## State model (JSON)

Minimal durable schema stored in `nbqueue/<session-id>/state.json`:

- `queue: [QueueItem]`
- `history: [QueueItem]`
- `current: QueueItem | null`
- `stop_requested: boolean` (optional)

QueueItem fields:
- `id: string` (ULID/timestamp)
- `original_path: string` (abs path)
- `queue_path: string` (abs path under `queue/`)
- `added_at: string` (ISO8601)
- `started_at: string` (ISO8601, optional)
- `ended_at: string` (ISO8601, optional)
- `status: "queued" | "running" | "done" | "failed" | "canceled"`
- `tag: string | null`
- `success: boolean | null`
- `returncode: number | null`
- `run_dir: string | null` (abs path under `output/<run-id>`)
- `pid: number | null`, `pgid: number | null`
- `error: string | null`

Writes to `state.json` are atomic: write `state.json.tmp` then rename.

## Process management

- Launch child with `start_new_session=True` so the child becomes a process group leader.
- Store child PID and PGID in `state.current` to enable signals:
  - kill: SIGTERM → wait grace → SIGKILL; then mark canceled.
  - abort: kill current (if any), mark canceled, clear queue, raise stop flag.
- Handle stale locks by checking if the PID in `lock.pid` is alive.

## Execution strategy

- Use Papermill to execute notebooks; NBClient/nbconvert as needed.
- Always pass an explicit kernel (`--kernel python3`).
- Convert `.py` to `.ipynb` with Jupytext at execution time (within the run directory).

## Configuration

CLI flags and environment variables:
- `NBQ_HOME` to override base directory (`nbqueue` by default).
- `NBQ_DEFAULT_KERNEL` (fallback kernel name).
- `--timeout` per-cell; default `None`.
- `--watch` to keep worker alive.
- `--once` to process a single item and exit.
- `--grace` for kill/abort grace period.

## Edge cases and reliability

- Stale `lock.pid`: detect dead PID and remove lock.
- Corrupt `state.json`: recover to an empty state (queue=[], history=[], current=null).
- Missing/renamed source files after enqueue: mark failed gracefully and continue.
- Executor crash or BrokenPipe: capture `returncode` and error; don’t block the worker.
- If a notebook in the queue fails, set `status=failed` and continue with next item.
- SIGINT/SIGTERM on worker: release lock and exit cleanly.

## Acceptance criteria

- Can enqueue `.ipynb` and `.py`; status shows Tag/Elapsed correctly.
- Enqueue snapshots into `nbqueue/<session-id>/queue`, appending tag to filename; `.ipynb` outputs are cleared before saving.
- `run` processes items FIFO with a single worker enforced by `lock.pid`.
- At runtime, input is copied to `nbqueue/<session-id>/output/<run-id>/` and executed there.
- `.py` converted at runtime; executed `.ipynb` and logs saved under the run directory.
- `kill` terminates current process group and marks the item canceled.
- `abort` kills current, clears queue (by default), and stops the worker.
- Durable state across restarts; logs written per item; `latest_run` updated.

## Packaging and entrypoint

- `pyproject.toml` (uv or hatchling)
- Dependencies: `typer`, `rich`, `jupytext`, `papermill`, `nbconvert`
- Console script:
```toml
[project.scripts]
nbq = "nbqueue.cli:main"
```

### Module structure

- `nbqueue/`
  - `cli.py` (Typer app, commands)
  - `worker.py` (run loop, lock/stop handling)
  - `exec.py` (conversion + papermill execution)
  - `state.py` (read/write, schema helpers)
  - `ps.py` (process management utilities)
  - `utils.py` (time formatting, path helpers)

## Testing strategy

### Unit tests (pytest)
- State read/write, atomic persistence, and schema defaults.
- Lock acquisition/release and stale lock recovery.
- Elapsed time formatting and status transitions.

### Integration tests
- Execute trivial `.ipynb` (with cleared outputs on enqueue) and trivial `.py` (Jupytext), assert `status.json` and artifacts under `output/<run-id>/`.
- Kill current run and assert `status=canceled`; queue proceeds on next run.
- Abort clears queue and stops worker.

### E2E smoke
- `nbq add`; `nbq run --once`; `nbq status`; `nbq clear`.

## Try it

Install with uv:
```bash
uv sync
```

Or with pip:
```bash
pip install .
```

Example commands:
```bash
nbq add --tag tester examples/demo.ipynb
nbq add --tag tester --start examples/demo.py
nbq run --watch
nbq status
nbq kill
nbq abort
```

## Future enhancements

- Duplicate detection and collapse by content hash + tag.
- Configurable retention and pruning (e.g., keep last N runs).
- `nbq open <run-id>` to open the executed notebook.
- Windows support with alternate signaling model.
