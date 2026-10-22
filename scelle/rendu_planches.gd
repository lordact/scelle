extends SceneTree
# Rend chaque modèle de res://Modeles/ (un projet temporaire monté par
# scelle.py planches) dans res://rendus/<nom>.png, vu de trois quarts haut.


func _init() -> void:
	var racine := Node3D.new()
	get_root().add_child(racine)
	var monde := WorldEnvironment.new()
	var env := Environment.new()
	var ciel := Sky.new()
	ciel.sky_material = ProceduralSkyMaterial.new()
	env.sky = ciel
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.13, 0.13, 0.15)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	monde.environment = env
	racine.add_child(monde)
	var soleil := DirectionalLight3D.new()
	soleil.rotation_degrees = Vector3(-35, 25, 0)
	racine.add_child(soleil)
	var camera := Camera3D.new()
	camera.fov = 30
	racine.add_child(camera)
	DirAccess.make_dir_recursive_absolute("res://rendus")
	await process_frame
	for f in DirAccess.open("res://Modeles").get_files():
		if not f.ends_with(".glb"):
			continue
		var modele: Node3D = load("res://Modeles/" + f).instantiate()
		racine.add_child(modele)
		var booster := f.begins_with("booster")
		var ouvert := f.contains("ouvert")
		var cible := Vector3(0, 0.0575 if booster else (0.08 if ouvert else 0.062), 0)
		var oeil := Vector3(0.03, 0.075, 0.19) if booster else (Vector3(0.12, 0.2, 0.36) if ouvert else Vector3(0.14, 0.12, 0.33))
		camera.look_at_from_position(oeil, cible)
		for i in 3:
			await process_frame
		get_root().get_texture().get_image().save_png("res://rendus/%s.png" % f.get_basename())
		modele.queue_free()
		await process_frame
	quit()
