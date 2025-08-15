# Usage

This page shows how to use nbq with uv and demonstrates the main functionality.

## Install (uv)

- bash
  uv sync

## CLI overview

- bash
  uv run nbq --help

Commands:
- add: Enqueue one or more `.ipynb` or `.py` files (optional tag, optional start worker)
- status: Show running and queued items (table or JSON)
- run: Process queued items (once or watch mode)
- clear: Clear pending queue (keeps current and history)
- cancel: Ask worker to stop after finishing current run
- kill: Terminate current run now (SIGTERM then SIGKILL)
- abort: Kill current, clear queue (by default), and stop worker

## Basic workflow

- Enqueue files:
  - bash
    uv run nbq add --tag demo examples/demo.py
    uv run nbq add --tag demo examples/demo.ipynb

- Run a single item and exit:
  - bash
    uv run nbq run --once

- Keep running and pick up new items:
  - bash
    uv run nbq run --watch

- Status:
  - bash
    uv run nbq status
    uv run nbq status --json

- Controls:
  - bash
    uv run nbq cancel
    uv run nbq kill --grace 5
    uv run nbq abort --grace 5

- Clear pending items:
  - bash
    uv run nbq clear --yes

## Tagging and enqueue rules

- `--tag TAG` attaches metadata and is appended to the snapshot filename in `queue/`:
  - `.py` → `<stem>_<tag>.py`
  - `.ipynb` → `<stem>_<tag>.ipynb`
- `.ipynb` outputs are cleared on enqueue to keep inputs clean.
- Original file paths are preserved in metadata.

## Execution behavior

- Each run executes in a dedicated `output/<run-id>/` directory:
  - `source.ext`: copied input
  - `input.ipynb`: `.ipynb` to execute (converted from `.py` if needed)
  - `executed.ipynb`: executed output
  - `run.log`: combined stdout/stderr stream
  - `status.json`: result (success/returncode/timings/error)
- `.py` files are converted using Jupytext at runtime before execution.
- Execution uses Papermill with an explicit kernel (default `python3`).

## Single worker and signals

- Only one worker is active per session (enforced by `lock.pid`).
- `kill` sends SIGTERM to the process group, then SIGKILL after the grace period and marks the run as canceled.
- `abort` kills current, clears queue (by default), and sets a stop flag so the worker exits.

## Directories and environment

Default base directory is `./nbqueue` (override with `NBQ_HOME`):

- nbqueue/<session-id>/
  - queue/ — pending inputs (snapshots from enqueue)
  - output/<run-id>/ — per-run outputs and logs
  - logs/
  - state.json
  - lock.pid
  - latest_run → output/<run-id>

Environment variables:
- `NBQ_HOME`: override base directory (default `./nbqueue`)
- `NBQ_DEFAULT_KERNEL`: kernel name for execution (default `python3`)

## Timeouts

Set a per-cell timeout:
- bash
  uv run nbq run --timeout 600
