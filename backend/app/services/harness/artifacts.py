from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactRef:
    name: str
    object_key: str | None = None
    path: str | None = None
    sha256: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
