"""Vérifier un .glb sans Godot : en-tête, morceaux, accesseurs, images, nœuds."""
import io
import json
import struct

from PIL import Image


def lire_glb(chemin):
	with open(chemin, "rb") as f:
		donnees = f.read()
	magie, version, longueur = struct.unpack_from("<III", donnees, 0)
	assert magie == 0x46546C67, "pas un glb"
	assert version == 2, "glTF %d" % version
	assert longueur == len(donnees), "longueur annoncée %d, réelle %d" % (longueur, len(donnees))
	lj, tj = struct.unpack_from("<II", donnees, 12)
	assert tj == 0x4E4F534A, "premier morceau pas JSON"
	j = json.loads(donnees[20:20 + lj])
	lb, tb = struct.unpack_from("<II", donnees, 20 + lj)
	assert tb == 0x004E4942, "second morceau pas BIN"
	binaire = donnees[28 + lj:28 + lj + lb]
	return j, binaire


def verifier_glb(chemin):
	"""Liste des problèmes (vide si le fichier est bon) et le nombre de boosters dedans."""
	problemes = []
	try:
		j, binaire = lire_glb(chemin)
	except (AssertionError, struct.error, ValueError) as e:
		return ["%s : %s" % (chemin, e)], 0
	vues = j.get("bufferViews", [])
	for i, v in enumerate(vues):
		if v["byteOffset"] + v["byteLength"] > len(binaire):
			problemes.append("vue %d hors du tampon" % i)
	tailles = {5126: 4, 5125: 4, 5123: 2}
	composants = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
	for i, a in enumerate(j.get("accessors", [])):
		v = vues[a["bufferView"]]
		if a["count"] * tailles[a["componentType"]] * composants[a["type"]] > v["byteLength"]:
			problemes.append("accesseur %d plus long que sa vue" % i)
	for i, im in enumerate(j.get("images", [])):
		v = vues[im["bufferView"]]
		try:
			Image.open(io.BytesIO(binaire[v["byteOffset"]:v["byteOffset"] + v["byteLength"]])).verify()
		except Exception as e:   # image illisible
			problemes.append("image %d illisible : %s" % (i, e))
	for i, m in enumerate(j.get("meshes", [])):
		for p in m["primitives"]:
			if p.get("material", 0) >= len(j.get("materials", [])):
				problemes.append("maillage %d : matériau absent" % i)
			n_idx = j["accessors"][p["indices"]]["count"]
			n_pos = j["accessors"][p["attributes"]["POSITION"]]["count"]
			if n_idx % 3 or n_pos == 0:
				problemes.append("maillage %d : triangles incomplets" % i)
	for i, n in enumerate(j.get("nodes", [])):
		if "mesh" in n and n["mesh"] >= len(j.get("meshes", [])):
			problemes.append("nœud %d : maillage absent" % i)
	boosters = sum(1 for n in j.get("nodes", []) if n.get("name", "").startswith("Booster"))
	return ["%s : %s" % (chemin, p) for p in problemes], boosters
