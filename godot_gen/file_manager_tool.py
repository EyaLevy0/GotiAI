"""FileManagerTool — safe filesystem access, scoped to the project directory.

No LLM calls. No Godot logic. Just files."""

from __future__ import annotations

from pathlib import Path
from typing import List


class FileManagerError(Exception):
    pass


class FileManagerTool:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()
        self.project_root.mkdir(parents=True, exist_ok=True)

    # -------- public --------

    def write(self, relative_path: str, content: str) -> Path:
        target = self._resolve_inside(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def read(self, relative_path: str) -> str:
        return self._resolve_inside(relative_path).read_text(encoding="utf-8")

    def exists(self, relative_path: str) -> bool:
        try:
            return self._resolve_inside(relative_path).exists()
        except FileManagerError:
            return False

    def list(self, relative_path: str = ".") -> List[str]:
        base = self._resolve_inside(relative_path)
        if not base.exists():
            return []
        return [
            str(p.relative_to(self.project_root).as_posix())
            for p in base.rglob("*")
            if p.is_file()
        ]

    def ensure_dir(self, relative_path: str) -> Path:
        target = self._resolve_inside(relative_path)
        target.mkdir(parents=True, exist_ok=True)
        return target

    # -------- safety --------

    def _resolve_inside(self, relative_path: str) -> Path:
        rel = Path(relative_path)
        if rel.is_absolute():
            raise FileManagerError(f"Absolute paths are not allowed: {relative_path}")
        resolved = (self.project_root / rel).resolve()
        try:
            resolved.relative_to(self.project_root)
        except ValueError as e:
            raise FileManagerError(f"Path escapes project root: {relative_path}") from e
        return resolved
