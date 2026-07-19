from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Iterator


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    passed: bool = False
    summary: dict | None = None


@contextmanager
def ephemeral_workspace(prefix: str = "mirai_harness_") -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        yield Path(tmp)
