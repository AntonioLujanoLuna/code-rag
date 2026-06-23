from __future__ import annotations

from pydantic import BaseModel


class ChangedFile(BaseModel):
    old_path: str
    new_path: str
    added: bool = False
    deleted: bool = False
    renamed: bool = False
    modified: bool = False
