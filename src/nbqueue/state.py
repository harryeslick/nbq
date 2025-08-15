from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import atomic_write_json, base_dir, ensure_dir, iso_now, timestamp_id, sanitize_tag, read_json

STATE_FILENAME = "state.json"
LOCK_FILENAME = "lock.pid"

@dataclass
class QueueItem:
    id: str
    original_path: str
    queue_path: str
    added_at: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    status: str = "queued"  # queued | running | done | failed | canceled
    tag: Optional[str] = None
    success: Optional[bool] = None
    returncode: Optional[int] = None
    run_dir: Optional[str] = None
    pid: Optional[int] = None
    pgid: Optional[int] = None
    error: Optional[str] = None

    @staticmethod
    def make(original_path: Path, queue_path: Path, tag: Optional[str]) -> "QueueItem":
        return QueueItem(
            id=timestamp_id(),
            original_path=str(original_path.resolve()),
            queue_path=str(queue_path.resolve()),
            added_at=iso_now(),
            status="queued",
            tag=sanitize_tag(tag),
        )

@dataclass
class State:
    queue: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    current: Optional[Dict[str, Any]] = None
    stop_requested: bool = False

    @staticmethod
    def default() -> "State":
        return State()

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "State":
        try:
            return State(
                queue=list(d.get("queue", [])),
                history=list(d.get("history", [])),
                current=d.get("current"),
                stop_requested=bool(d.get("stop_requested", False)),
            )
        except Exception:
            return State.default()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queue": self.queue,
            "history": self.history,
            "current": self.current,
            "stop_requested": self.stop_requested,
        }

class Session:
    def __init__(self, root: Path):
        self.root = root
        self.queue_dir = self.root / "queue"
        self.output_dir = self.root / "output"
        self.logs_dir = self.root / "logs"
        self.state_path = self.root / STATE_FILENAME
        self.lock_path = self.root / LOCK_FILENAME
        self.latest_run_link = self.root / "latest_run"

    def ensure_layout(self) -> None:
        ensure_dir(self.root)
        ensure_dir(self.queue_dir)
        ensure_dir(self.output_dir)
        ensure_dir(self.logs_dir)
        if not self.state_path.exists():
            save_state(self, State.default())

def sessions_base() -> Path:
    return base_dir()

def new_session() -> Session:
    sid = timestamp_id()
    root = sessions_base() / sid
    s = Session(root)
    s.ensure_layout()
    return s

def list_sessions() -> list[Session]:
    base = sessions_base()
    ensure_dir(base)
    sessions: list[Session] = []
    for child in base.iterdir():
        if child.is_dir() and (child / STATE_FILENAME).exists():
            sessions.append(Session(child))
    sessions.sort(key=lambda x: x.root.name)
    return sessions

def read_lock_pid(session: Session) -> Optional[int]:
    try:
        txt = (session.lock_path).read_text(encoding="utf-8").strip()
        if not txt:
            return None
        return int(txt)
    except Exception:
        return None

def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def active_session() -> Optional[Session]:
    for s in reversed(list_sessions()):
        pid = read_lock_pid(s)
        if pid and is_pid_alive(pid):
            return s
    return None

def latest_session() -> Optional[Session]:
    sessions = list_sessions()
    return sessions[-1] if sessions else None

def get_or_create_session() -> Session:
    s = active_session()
    if s:
        return s
    s2 = latest_session()
    if s2:
        return s2
    return new_session()

def load_state(session: Session) -> State:
    data = read_json(session.state_path, default=State.default().to_dict())
    return State.from_dict(data)

def save_state(session: Session, state: State) -> None:
    atomic_write_json(session.state_path, state.to_dict())

def append_queue(session: Session, item: QueueItem) -> None:
    st = load_state(session)
    st.queue.append(asdict(item))
    save_state(session, st)

def clear_queue(session: Session) -> None:
    st = load_state(session)
    st.queue = []
    save_state(session, st)
