# nbq

A single-worker queue for executing Jupyter notebooks one at a time with a simple CLI. Supports tagging runs, live status, safe cancel/kill, and reliable artifact capture.

## Features

- Single active run; remaining items queued FIFO
- Works with `.ipynb` and `.py` (Jupytext percent scripts)
- Durable state and per-run artifacts (executed notebook, logs, status)
- Safe cancel/kill/abort with process-group signaling
- Clear CLI with `add`, `status`, `run`, `clear`, `cancel`, `kill`, `abort`

## Install and run (uv)

- Install dependencies:
  - bash
    uv sync

- Use the CLI:
  - bash
    uv run nbq --help

## Quickstart

- Enqueue notebooks or scripts:
  - bash
    uv run nbq add --tag demo examples/demo.py
    uv run nbq add --tag demo examples/demo.ipynb

- Process one item:
  - bash
    uv run nbq run --once

- Keep a worker running and pick up new items:
  - bash
    uv run nbq run --watch

- Check status (table or JSON):
  - bash
    uv run nbq status
    uv run nbq status --json

- Control the worker:
  - bash
    uv run nbq cancel
    uv run nbq kill --grace 5
    uv run nbq abort --grace 5

## Directory layout

By default, `NBQ_HOME=./nbqueue` (override with environment variable `NBQ_HOME`).

- nbqueue/<session-id>/
  - queue/ – pending inputs (snapshotted copies from enqueue)
  - output/<run-id>/ – per-run outputs
    - source.ext – the copied input used for execution
    - executed.ipynb – executed notebook
    - run.log – stdout/stderr stream
    - status.json – run result metadata
  - logs/ – optional additional logs
  - state.json – queue, history, current, stop flags
  - lock.pid – single-worker enforcement
  - latest_run -> output/<run-id> – symlink to latest run (best-effort)

## Execution details

- `.py` inputs are converted to `.ipynb` using Jupytext within the run directory
- Execution uses Papermill with an explicit kernel (default `python3`, override with `NBQ_DEFAULT_KERNEL`)
- Per-cell timeout can be set via `nbq run --timeout SECONDS`
- Output notebooks and logs are written under each run’s directory

## Environment variables

- `NBQ_HOME` – base directory for sessions (default `./nbqueue`)
- `NBQ_DEFAULT_KERNEL` – kernel name for execution (default `python3`)
