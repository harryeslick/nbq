# %% [markdown]
# # nbq notebook example
#
# This page is generated from a Jupytext percent script.
# It demonstrates safe, lightweight use of the library objects inside docs.
#
# To enqueue and run notebooks from a shell (not executed here), use:
#
# ```bash
# uv sync
# uv run nbq add --tag docs examples/demo.py
# uv run nbq run --once
# uv run nbq status
# ```

# %% [markdown]
# ## Inspect installation and sessions

# %%
from nbqueue import __version__
from nbqueue.state import list_sessions, latest_session

print("nbq version:", __version__)

sessions = list_sessions()
print(f"Found {len(sessions)} session(s).")
if sessions:
    print("Latest session path:", latest_session().root)

# %% [markdown]
# The commands above do not modify the queue. They just read existing session
# directories (if any) under `NBQ_HOME` (defaults to `./nbqueue`).
