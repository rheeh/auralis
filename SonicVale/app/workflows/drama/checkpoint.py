from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import getLangGraphCheckpointPath


@contextmanager
def open_drama_checkpointer() -> Iterator[SqliteSaver]:
    connection = sqlite3.connect(getLangGraphCheckpointPath(), check_same_thread=False)
    try:
        saver = SqliteSaver(connection)
        saver.setup()
        yield saver
    finally:
        connection.close()
