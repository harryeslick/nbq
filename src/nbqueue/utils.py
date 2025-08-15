from __future__ import annotations

import json
import os
import random
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import nbformat  # type: ignore
except Exception:  # pragma: no cover
    nbformat = None  # Will be required at runtime for .ipynb handling

SAFE_TAG_RE = re.compile(r"[^A-Za-z0-9_\-]+")

def base_dir() -> Path:
    """
    Resolve the NBQ home directory.
    Default is ./nbqueue (relative to CWD) unless NBQ_HOME is set.
    Returns an absolute Path.
    """
    env = os.environ.get("NBQ_HOME")
    if env:
        p = Path(env)
        return p if p.is_absolute() else (Path.cwd() / p).resolve()
    return (Path.cwd() / "nbqueue").resolve()

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def iso_now() -> str:
    # Truncate to seconds for stable diffs
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def timestamp_id() -> str:
    # Session ID friendly ISO-like (file-system safe)
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

def run_id() -> str:
    # Monotonic-ish, high-resolution
    return f"{int(time.time()*1000)}-{random.randrange(16**4):04x}"

def sanitize_tag(tag: Optional[str]) -> Optional[str]:
    if not tag:
        return None
    tag = tag.strip().replace(" ", "-")
    tag = SAFE_TAG_RE.sub("-", tag)
    tag = re.sub(r"-{2,}", "-", tag).strip("-")
    return tag or None

def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def copy_and_clear_ipynb(src: Path, dst: Path) -> None:
    """
    Copy .ipynb from src to dst, clearing outputs.
    Requires nbformat.
    """
    if nbformat is None:
        raise RuntimeError("nbformat is required to handle .ipynb files")
    nb = nbformat.read(str(src), as_version=4)
    for cell in nb.cells:
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
    nbformat.write(nb, str(dst))

def snapshot_source_to(dst_dir: Path, src_path: Path, tag: Optional[str]) -> Path:
    """
    Snapshot source file into dst_dir.
    - If .py and tag provided, filename becomes <stem>_<tag>.py
    - If .ipynb, clear outputs before saving; if tag provided, append to stem.
    Returns absolute snapshot path.
    """
    ensure_dir(dst_dir)
    src_path = src_path.resolve()
    ext = src_path.suffix.lower()
    stem = src_path.stem
    tag_s = sanitize_tag(tag)
    new_name = f"{stem}_{tag_s}{ext}" if tag_s else f"{stem}{ext}"
    dst_path = (dst_dir / new_name).resolve()
    if ext == ".ipynb":
        copy_and_clear_ipynb(src_path, dst_path)
    else:
        shutil.copy2(src_path, dst_path)
    return dst_path

def parse_iso(ts: str) -> datetime:
    """
    Parse ISO8601 timestamps we write (supports trailing 'Z').
    """
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)

def human_duration(seconds: float) -> str:
    """
    Render a compact human duration like '1h 02m 03s' or '5m 10s' or '12s'.
    """
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if h or m:
        parts.append(f"{m:02d}m" if h else f"{m}m")
    parts.append(f"{s:02d}s" if (h or m) else f"{s}s")
    return " ".join(parts)

def elapsed_since(ts_iso: str) -> str:
    """
    Compute human duration from given ISO time until now (UTC).
    """
    try:
        dt = parse_iso(ts_iso)
        now = datetime.now(timezone.utc)
        return human_duration((now - dt).total_seconds())
    except Exception:
        return "?"
