class_name SpriteLoader
extends RefCounted

# Load a simple PNG into a Sprite2D.
static func load_texture(sprite_node: Sprite2D, image_name: String) -> void:
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
