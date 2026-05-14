"""
File Manager Tool.

This tool is responsible for safe file operations inside the local Godot project
folder, such as creating directories, writing generated files, reading existing
project files, and listing files that already exist.
"""

from pathlib import Path
from typing import List


class FileManagerTool:
    """
    Handles file operations inside a specific Godot project directory.

    This tool does not generate code by itself.
    It only saves, reads, lists, and checks files that belong to the project.
    """

    def __init__(self, project_directory_path: str):
        # Store the Godot project root as a Path object for safer path handling.
        self.project_root = Path(project_directory_path).resolve()

    def _resolve_project_path(self, relative_file_path: str) -> Path:
        """
        Convert a relative project path into a safe absolute path.

        Example:
            scripts/player_controller.gd
            -> C:/some/project/scripts/player_controller.gd
        """

        target_path = (self.project_root / relative_file_path).resolve()

        # Prevent reading or writing outside the project folder by mistake.
        if self.project_root not in target_path.parents and target_path != self.project_root:
            raise ValueError(
                f"Unsafe file path detected: {relative_file_path}. "
                "Files must stay inside the Godot project directory."
            )

        return target_path

    def write_file(self, relative_file_path: str, content: str) -> Path:
        """
        Write content to a file inside the Godot project.

        Creates parent directories automatically if they do not exist.
        """

        target_path = self._resolve_project_path(relative_file_path)

        # Ensure the folder exists before writing the file.
        target_path.parent.mkdir(parents=True, exist_ok=True)

        target_path.write_text(content, encoding="utf-8")

        return target_path

    def read_file(self, relative_file_path: str) -> str:
        """
        Read and return the content of a file inside the Godot project.
        """

        target_path = self._resolve_project_path(relative_file_path)

        if not target_path.exists():
            raise FileNotFoundError(f"File not found: {relative_file_path}")

        return target_path.read_text(encoding="utf-8")

    def file_exists(self, relative_file_path: str) -> bool:
        """
        Check whether a file exists inside the Godot project.
        """

        target_path = self._resolve_project_path(relative_file_path)
        return target_path.exists()

    def ensure_directory(self, relative_directory_path: str) -> Path:
        """
        Create a directory inside the Godot project if it does not already exist.
        """

        target_path = self._resolve_project_path(relative_directory_path)
        target_path.mkdir(parents=True, exist_ok=True)

        return target_path

    def list_files(self, relative_directory_path: str = "") -> List[str]:
        """
        List all files inside a project directory.

        Returns relative paths so other tools can compare them with planned
        dependency paths such as scripts/player_controller.gd.
        """

        target_directory = self._resolve_project_path(relative_directory_path)

        if not target_directory.exists():
            return []

        if not target_directory.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {relative_directory_path}"
            )

        files: List[str] = []

        # Recursively collect only files, not folders.
        for path in target_directory.rglob("*"):
            if path.is_file():
                relative_path = path.relative_to(self.project_root)
                files.append(relative_path.as_posix())

        return sorted(files)