# nbqueue – Design and Implementation Plan (Standalone Package)

A single-worker queue for executing Jupyter notebooks (and Python “percent” notebooks via Jupytext) one at a time with a simple CLI. Supports tagging runs, live status, safe cancel/kill, and reliable artifact capture.

## Purpose

- Execute one notebook at a time (.ipynb or .py via Jupytext) with robust CLI controls.
- Provide durable state, resumability, logs, and artifact capture.

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
- For .py files, convert to .ipynb at using Jupytext.

## CLI specification

### nbq add
```bash
nbq add [--tag TAG] PATH [--run] ...
```
- Accepts relative or absolute paths.
- use run flag to execute nbq run apon adding file to queue


### nbq status
```bash
nbq status
```
- Shows: ID, Notebook, Tag, Status, Elapsed, Result (success/returncode).
- Elapsed is “since started_at” for running and “since added_at” for queued.
- retains all completed items within the current session

### nbq run
```bash
nbq run [--timeout SECONDS] [--watch]
```
- Processes one at a time; optional per-cell timeout forwarded to executor.
- `--watch` keeps the worker alive to pick up newly added items.

### nbq clear
```bash
nbq clear --yes
```
- Clears pending queue (does not touch current run).

### nbq cancel
```bash
nbq cancel
```
- Creates a stop flag; the worker exits after finishing the current notebook.

### nbq kill
```bash
nbq kill [--grace SECONDS]
```
- Sends SIGTERM to the running notebook’s process group, then SIGKILL after a grace period; marks the run as canceled.

### nbq abort
```bash
nbq abort [--grace SECONDS] [--no-clear-queue]
```
- Kills current run (if any), marks it canceled, clears queue by default, and raises the stop flag.

## Behavior and data flow

### Enqueue
- create local directory to hold queue, outputs and logs. use `nbqueue` as default. allow for user override on CLI
- check for currently active session. if active session exists, use existing session folder `nbqueue/<session-id>/queue`. 
- otherwise, create a session folder `nbqueue/<session-id>/queue`. 
- copy Enqueued file into the `nbqueue/<session-id>/queue` direcotry. append filename with `tag`

### Run loop
- Acquire a single-worker lock (`lock.pid`). If another worker is alive, exit.
- execute files within `nbqueue/<session-id>/queue` in FIFO order. 

### Execute notebook
- For .py: Convert to a temp `.ipynb` using Jupytext (respecting cell markers).
- Pass a default kernel (`--kernel python3`) to avoid missing kernelspec.
- save completed notebooks as `.ipynb` to `nbqueue/<session-id>/queue` to allow user to review the output cells. 

## Process management

- Launch child with `start_new_session=True` so the child becomes a process group leader.
- Store child PID and PGID in `state.current` to enable signals:
  - kill: SIGTERM → wait grace → SIGKILL; then mark canceled.
  - abort: kill current (if any), mark canceled, clear queue, raise stop flag.
- Handle stale locks by checking if the PID in `lock.pid` is alive.

## Execution strategy

- Use Papermill to execute notebooks; NBClient/nbconvert as needed.
- Always pass an explicit kernel (`--kernel python3`).


## Packaging and entrypoint

- `pyproject.toml` (uv)
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

## Configuration

CLI flags and environment variables:
- `NBQ_HOME` to override state/logs directory.
- `NBQ_DEFAULT_KERNEL` (fallback kernel name).
- `--timeout` per-cell; default `None`.
- `--watch` to keep worker alive.
- `--grace` for kill/abort grace period.

## Edge cases and reliability

- Stale `lock.pid`: detect dead PID and remove lock.
- Corrupt `state.json`: recover to an empty state.
- Missing/renamed source files after enqueue: mark failed gracefully.
- Executor crash or BrokenPipe: capture returncode and error; don’t block the worker.
- If notebook in que exists with error, set the status to `failed` and continue to the next item in queue
- SIGINT/SIGTERM on worker: release lock and exit cleanly.

## Acceptance criteria

- Can enqueue `.ipynb` and `.py`; status shows Tag/Elapsed correctly.
- `run` processes items FIFO.
- set number of workers with a flag at run default behaviour to use a single worker only
- `.py` converted at runtime; original `.py` copied with tag into run dir.
- `kill` terminates current process group and marks the item canceled.
- `abort` kills current, clears queue, and stops the worker.
- Durable state across restarts; logs written per item.
- Console script `nbq` available after install.

## Testing strategy

### Unit tests
- testing using pytest
- State read/write and schema defaults.
- Lock acquisition/release and stale lock recovery.
- Elapsed time formatting.

### Integration tests
- Execute a trivial notebook (`.ipynb`) and a trivial `.py` (Jupytext) and assert `status.json` and artifacts exist.
- Kill current run and assert `status=canceled`; queue proceeds on next run.
- Abort clears queue and stops the worker.



## Try it

Install with uv:
```bash
uv sync
```

Example commands:
```bash
nbq add examples/demo.ipynb
nbq add --tag test examples/demo.py
nbq run --watch
nbq status
nbq kill
nbq abort
```
