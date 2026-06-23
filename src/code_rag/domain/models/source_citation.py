from __future__ import annotations

from pydantic import BaseModel


class SourceCitation(BaseModel):
    index: int
    repo_path_with_namespace: str
    file_path: str
    line_start: int
    line_end: int
    url: str
