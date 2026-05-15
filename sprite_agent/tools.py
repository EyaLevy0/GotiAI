"""Tools for the Sprite Agent (A3).

The main tool, `inject_kit_assets`, copies a selected asset kit into the
Godot project and writes a helper `SpriteLoader.gd` file. It intentionally
avoids generating `.tres` files and keeps all animation setup in GDScript.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from langchain_core.tools import tool


def _build_sprite_loader_script() -> str:
    """Return the Godot 4.x GDScript helper used by the Sprite Agent."""

    return """class_name SpriteLoader
extends RefCounted

# Load a simple PNG into a Sprite2D.
static func load_texture(sprite_node: Sprite2D, image_name: str) -> void:
	var path = "res://assets/" + image_name
	if ResourceLoader.exists(path):
		sprite_node.texture = load(path)
	else:
		push_error("Texture not found: " + path)

# Build SpriteFrames at runtime from animation subfolders.
static func setup_animations(animated_sprite: AnimatedSprite2D, character_folder: String) -> void:
	var frames = SpriteFrames.new()
	var base_path = "res://assets/animations/" + character_folder + "/"
	var dir = DirAccess.open(base_path)

	if dir == null:
		push_error("Animation folder not found: " + base_path)
		return

	for anim_name in dir.get_directories():
		var anim_path = base_path + anim_name + "/"
		var anim_dir = DirAccess.open(anim_path)
		if anim_dir == null:
			continue

		var frame_files: Array[String] = []
		for file_name in anim_dir.get_files():
			if file_name.to_lower().ends_with(".png"):
				frame_files.append(file_name)

		frame_files.sort()
		if not frames.has_animation(anim_name):
			frames.add_animation(anim_name)
		frames.set_animation_loop(anim_name, true)
		frames.set_animation_speed(anim_name, 5.0)

		for frame_file in frame_files:
			var tex = load(anim_path + frame_file)
			if tex:
				frames.add_frame(anim_name, tex)

	animated_sprite.sprite_frames = frames
"""


def _copy_kit_tree(selected_kit: str, godot_project_path: str) -> tuple[Path, Path]:
    """Copy the chosen kit into the project assets directory and return paths."""

    source_kit_dir = Path("kits") / selected_kit
    target_assets_dir = Path(godot_project_path) / "assets"

    if not source_kit_dir.exists():
        raise FileNotFoundError(f"Kit '{selected_kit}' not found at {source_kit_dir}")

    target_assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_kit_dir, target_assets_dir, dirs_exist_ok=True)
    return source_kit_dir, target_assets_dir


def _write_sprite_loader(godot_project_path: str) -> Path:
    """Write the SpriteLoader.gd helper into the Godot project root."""

    gdscript_path = Path(godot_project_path) / "SpriteLoader.gd"
    gdscript_path.write_text(_build_sprite_loader_script(), encoding="utf-8")
    return gdscript_path


@tool("inject_kit_assets")
def inject_kit_assets(selected_kit: str, godot_project_path: str) -> str:
    """Inject a selected kit into the Godot project and generate SpriteLoader.gd.

    This tool copies `kits/<selected_kit>` into `<project>/assets` and writes a
    Godot 4.x helper script at `<project>/SpriteLoader.gd`. It does not create
    `.tres` files.
    """

    try:
        source_kit_dir, target_assets_dir = _copy_kit_tree(selected_kit, godot_project_path)
        gdscript_path = _write_sprite_loader(godot_project_path)
    except Exception as exc:
        return f"ERROR: {exc}"

    return (
        f"Success: injected '{selected_kit}' from {source_kit_dir} into {target_assets_dir} "
        f"and created {gdscript_path}"
    )
