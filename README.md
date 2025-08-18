# nbqueue (CLI: nbq)

Run Jupyter notebooks one-by-one with a simple queue and clear results.

`nbqueue` gives you a tiny, reliable queue. You add notebooks (or percent-formatted .py scripts), and a single worker executes them in order.

## What you get

- Single-worker execution (no overlapping runs)
- Durable on-disk state and per-run artifacts
- Works with .ipynb and Jupytext percent scripts (.py)
- Easy control: add, status, run, clear, cancel, kill, abort
- Friendly CLI with Rich + Typer
- Status includes the worker PID; terminating it stops the current run and empties the queue

## Quickstart (with uv)

Requires Python 3.9+ and [uv](https://github.com/astral-sh/uv)

```bash
# Install dependencies and build the local package
uv sync

# Enqueue a notebook or percent-formatted script
uv run nbq add examples/demo.py
uv run nbq add examples/demo.ipynb

# Process one item and exit
uv run nbq run --once

# See what's going on
uv run nbq status

# Keep a worker running and handle new items as they arrive
uv run nbq run --watch

# If a worker is already running, nbq run will no-op and print its PID
uv run nbq run
```

Control the worker:

```bash
# Finish current run then stop
uv run nbq cancel

# Try graceful stop (SIGTERM), then force (SIGKILL) after grace seconds
uv run nbq kill --grace 10

# Kill current, mark canceled, clear queue (default), and stop
uv run nbq abort
```

Useful flags:

```bash
# Exit if no work arrives within 60s
uv run nbq run --timeout 60

# Ensure exactly one item is processed
uv run nbq run --once
```

## What happens under the hood

- .py percent scripts → converted to .ipynb at runtime (Jupytext)
- Execution → Papermill (kernel default: python3; override with NBQ_DEFAULT_KERNEL)
- State is durable JSON on disk, updated atomically
- One worker at a time enforced via a PID lock
- If a worker is already active, `nbq run` warns and exits without starting another

## Where files go (default NBQ_HOME=./nbqueue)

- `nbqueue/<session-id>/state.json` — queue state (queue, history, current, stop flag)
- `nbqueue/<session-id>/lock.pid` — single-worker lock (PID of the worker)
- `nbqueue/<session-id>/queue/` — snapshots of enqueued items
- `nbqueue/<session-id>/<run-id>/` — per-run artifacts live directly under the session root
	- `source.ext` — original snapshot (.py or .ipynb)
	- `input.ipynb` — notebook to execute (converted from .py if needed)
	- `executed.ipynb` — executed output
	- `run.log` — stdout/stderr
	- `status.json` — result metadata (success, returncode, error)
- `nbqueue/<session-id>/latest_run` → symlink to the last run directory

## Configuration

- `NBQ_HOME` — base directory (default: ./nbqueue)
- `NBQ_DEFAULT_KERNEL` — Jupyter kernel (default: python3)

CLI command stays `nbq`; package name is `nbqueue`.

## Learn more

Build and open the docs locally:

```bash
mkdocs serve
```
