"""Les modèles 3D du scellé : géométrie et écriture glTF (.glb).

Booster (sachet bombé, bandes serties en dents de scie), demi-display de 12 et
display de 24, fermés (couvercle à jupe) ou ouverts (façade prédécoupée
arrachée, couvercle relevé en en-tête, boosters debout dedans). Échelle réelle,
en mètres ; origine au centre de la base, face avant vers +Z.
"""
import io
import json
import math
import os
import struct

import numpy as np
from PIL import Image

import chemins
import visuels as da

# Dimensions (m).
BOOSTER_L, BOOSTER_H, BOOSTER_E = 0.072, 0.115, 0.0058   # largeur, hauteur, épaisseur au centre
SERTI = 0.008                                           # bandes serties haut et bas
PAS = 0.0062                                            # un booster debout dans la boîte
PAROI = 0.0025                                          # carton
HAUT_BOITE = 0.124
COUVERCLE = 0.022                                       # jupe du couvercle
FACADE_OUVERTE = 0.042                                  # façade prédécoupée, une fois arrachée
PX_M = 5200                                             # densité des textures de boîte (px par m)

# --------------------------------------------------------------------------- atlas

class Atlas:
	"""Range des Calques dans une texture (et leur dorure) et donne leurs rectangles UV."""

	def __init__(self, cote=2048):
		self.c = da.Calque(cote, cote, (40, 40, 40))
		self.x = self.y = self.ligne = 0
		self.uv = {}
		self.rect = {}

	def ajouter(self, nom, calque):
		c = self.c.w
		if self.x + calque.w > c:
			self.x, self.y, self.ligne = 0, self.y + self.ligne + 4, 0
		assert self.y + calque.h <= c, "atlas trop petit pour " + nom
		self.c.img.paste(calque.img, (self.x, self.y))
		self.c.dorure.paste(calque.dorure, (self.x, self.y))
		self.rect[nom] = (self.x, self.y, calque.w, calque.h)
		self.uv[nom] = ((self.x + 1) / c, (self.y + 1) / c, (self.x + calque.w - 1) / c, (self.y + calque.h - 1) / c)
		self.x += calque.w + 4
		self.ligne = max(self.ligne, calque.h)


def px(m):
	return max(8, int(round(m * PX_M)))


# --------------------------------------------------------------------------- géométrie

class Maillage:
	def __init__(self):
		self.pos, self.nrm, self.uv, self.idx = [], [], [], []

	def quad(self, p0, p1, p2, p3, uv):
		"""p0 bas-gauche, p1 bas-droite, p2 haut-droite, p3 haut-gauche, vus de l'extérieur."""
		u0, v0, u1, v1 = uv
		p = [np.array(q, float) for q in (p0, p1, p2, p3)]
		n = np.cross(p[1] - p[0], p[3] - p[0])
		n /= np.linalg.norm(n)
		b = len(self.pos)
		self.pos += p
		self.nrm += [n] * 4
		self.uv += [(u0, v1), (u1, v1), (u1, v0), (u0, v0)]
		self.idx += [b, b + 1, b + 2, b, b + 2, b + 3]

	def pave(self, mn, mx, faces):
		"""Pavé aligné sur les axes ; faces : {"avant","arriere","gauche","droite","dessus","dessous"} -> uv."""
		x0, y0, z0 = mn
		x1, y1, z1 = mx
		f = faces
		self.quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), f["avant"])
		self.quad((x1, y0, z0), (x0, y0, z0), (x0, y1, z0), (x1, y1, z0), f["arriere"])
		self.quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0), f["gauche"])
		self.quad((x1, y0, z1), (x1, y0, z0), (x1, y1, z0), (x1, y1, z1), f["droite"])
		self.quad((x0, y1, z1), (x1, y1, z1), (x1, y1, z0), (x0, y1, z0), f["dessus"])
		self.quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), f["dessous"])


def sous_uv(uv, a0, b0, a1, b1):
	"""Partie d'un rectangle UV (fractions horizontales a, verticales b depuis le haut)."""
	u0, v0, u1, v1 = uv
	return (u0 + (u1 - u0) * a0, v0 + (v1 - v0) * b0, u0 + (u1 - u0) * a1, v0 + (v1 - v0) * b1)


def maillage_booster():
	"""Sachet bombé, bords latéraux soudés, bandes serties en dents de scie."""
	nx, ny = 24, 40
	m = Maillage()
	xs = np.linspace(-BOOSTER_L / 2, BOOSTER_L / 2, nx + 1)
	ys = np.concatenate([[0.0], np.linspace(SERTI, BOOSTER_H - SERTI, ny - 1), [BOOSTER_H]])

	def epaisseur(x, y):
		fx = max(0.0, 1 - abs(2 * x / BOOSTER_L) ** 6) ** 0.5
		if y <= SERTI or y >= BOOSTER_H - SERTI:
			fy = 0.0
		else:
			t = min(y - SERTI, BOOSTER_H - SERTI - y) / 0.012
			fy = min(1.0, t) ** 0.6
		return 0.00025 + (BOOSTER_E / 2 - 0.00025) * fx * fy

	for face, sens in (("avant", 1), ("arriere", -1)):
		grille = np.zeros((ny + 1, nx + 1, 3))
		for j, y in enumerate(ys):
			for i, x in enumerate(xs):
				yy = y
				if j in (0, ny):
					yy += (0.0012 if j == 0 else -0.0012) * (i % 2)   # dents de scie
				grille[j, i] = (x, yy, sens * epaisseur(x, y))
		# normales par différences finies
		dx = np.gradient(grille, axis=1)
		dy = np.gradient(grille, axis=0)
		normales = np.cross(dx, dy) * sens
		normales /= np.linalg.norm(normales, axis=2, keepdims=True)
		base = len(m.pos)
		for j in range(ny + 1):
			for i in range(nx + 1):
				m.pos.append(grille[j, i])
				m.nrm.append(normales[j, i])
				u = i / nx
				if face == "arriere":
					u = 1 - u
				m.uv.append(((u + (1 if face == "arriere" else 0)) * 0.5, 1 - grille[j, i][1] / BOOSTER_H))
		for j in range(ny):
			for i in range(nx):
				a = base + j * (nx + 1) + i
				b, c, d = a + 1, a + nx + 2, a + nx + 1
				if face == "avant":
					m.idx += [a, b, c, a, c, d]
				else:
					m.idx += [a, c, b, a, d, c]
	return m


def dims_display(nombre):
	rangs = nombre // 2
	int_l = 2 * BOOSTER_L + 0.004
	int_p = rangs * PAS + 0.002
	return int_l + 2 * PAROI, int_p + 2 * PAROI, HAUT_BOITE, rangs


def atlas_display(cle, serie, code, nombre):
	L, P, H, _ = dims_display(nombre)
	a = Atlas()
	a.ajouter("facade", da.facade(cle, serie, code, px(L), px(H), nombre))
	a.ajouter("dos", da.dos(cle, serie, code, px(L), px(H), nombre))
	a.ajouter("dessus", da.dessus(cle, serie, px(L), px(P)))
	a.ajouter("entete", da.entete(cle, serie, px(L), px(P)))
	a.ajouter("gauche", da.cote(cle, serie, code, px(P), px(H), nombre, 0))
	a.ajouter("droite", da.cote(cle, serie, code, px(P), px(H), nombre, 1))
	a.ajouter("jupe", da.jupe(serie, px(L), px(COUVERCLE)))
	a.ajouter("bande", da.bande_ouverte(cle, serie, px(L), px(FACADE_OUVERTE), nombre))
	a.ajouter("interieur", da.interieur(serie))
	return a


def avec_edition(a, serie, edition):
	"""Copie de l'atlas avec la mention d'édition en bas à gauche de la façade
	(boîte fermée) et de la bande qui reste une fois la façade arrachée."""
	c = da.Calque(a.c.w, a.c.h)
	c.img, c.dorure = a.c.img.copy(), a.c.dorure.copy()
	for panneau, (fx, fy, fr) in (("facade", da.EDITION_FACADE), ("bande", da.EDITION_BANDE)):
		x, y, w, h = a.rect[panneau]
		da.mention_edition(c, serie, edition, x + w * fx, y + h * fy, h * fr)
	return c


def maillage_display(a, nombre, ouvert):
	L, P, H, _ = dims_display(nombre)
	uv = a.uv
	c = uv["interieur"]
	m = Maillage()
	x0, x1, z0, z1 = -L / 2, L / 2, -P / 2, P / 2

	if not ouvert:
		# le fond porte les panneaux entiers ; leur haut passe sous la jupe du couvercle
		m.pave((x0, 0, z0), (x1, H - 0.001, z1), {"avant": uv["facade"], "arriere": uv["dos"],
			"gauche": uv["gauche"], "droite": uv["droite"], "dessus": c, "dessous": c})
		# le couvercle, un peu plus large que le fond
		e = 0.0012
		m.pave((x0 - e, H - COUVERCLE, z0 - e), (x1 + e, H, z1 + e), {
			"avant": uv["jupe"], "arriere": uv["jupe"],
			"gauche": sous_uv(uv["jupe"], 0, 0, P / L, 1), "droite": sous_uv(uv["jupe"], 1 - P / L, 0, 1, 1),
			"dessus": uv["dessus"], "dessous": c})
		return m, None

	t = PAROI
	hf = FACADE_OUVERTE
	m.pave((x0, 0, z0), (x1, t, z1), {**{k: c for k in ("arriere", "gauche", "droite", "dessus", "dessous")},
		"avant": sous_uv(uv["bande"], 0, 1 - t / hf, 1, 1)})
	# façade arrachée : seul le bas reste
	m.pave((x0, t, z1 - t), (x1, hf, z1), {"avant": sous_uv(uv["bande"], 0, 0, 1, 1 - t / hf), "arriere": c,
		"gauche": c, "droite": c, "dessus": c, "dessous": c})
	m.pave((x0, t, z0), (x1, H, z0 + t), {"avant": c, "arriere": sous_uv(uv["dos"], 0, 0, 1, 1 - t / H),
		"gauche": c, "droite": c, "dessus": c, "dessous": c})
	for sx, nom in ((x0, "gauche"), (x1 - t, "droite")):
		faces = {k: c for k in ("avant", "arriere", "gauche", "droite", "dessus", "dessous")}
		faces[nom] = sous_uv(uv[nom], 0, 0, 1, 1 - t / H)
		m.pave((sx, t, z0 + t), (sx + t, H, z1 - t), faces)
	# couvercle relevé à l'arrière : maillage local, articulé par le nœud
	volet = Maillage()
	volet.pave((x0, 0, 0), (x1, P, t), {"avant": uv["entete"], "arriere": sous_uv(uv["dessus"], 0, 0, 1, 1),
		"gauche": c, "droite": c, "dessus": c, "dessous": c})
	return m, volet


# --------------------------------------------------------------------------- glTF

class Gltf:
	def __init__(self):
		self.bin = bytearray()
		self.j = {"asset": {"version": "2.0", "generator": "Card Hustle generer_scelle.py"}, "scene": 0,
			"scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [], "textures": [], "images": [],
			"samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
			"accessors": [], "bufferViews": [], "buffers": []}

	def _vue(self, data, cible=None):
		while len(self.bin) % 4:
			self.bin.append(0)
		v = {"buffer": 0, "byteOffset": len(self.bin), "byteLength": len(data)}
		if cible:
			v["target"] = cible
		self.bin += data
		self.j["bufferViews"].append(v)
		return len(self.j["bufferViews"]) - 1

	def _acces(self, arr, type_, comp, cible, minmax=False):
		vue = self._vue(arr.tobytes(), cible)
		a = {"bufferView": vue, "componentType": comp, "count": len(arr), "type": type_}
		if minmax:
			a["min"], a["max"] = arr.min(axis=0).tolist(), arr.max(axis=0).tolist()
		self.j["accessors"].append(a)
		return len(self.j["accessors"]) - 1

	def _image(self, nom, img, format_, qualite):
		tampon = io.BytesIO()
		img.save(tampon, format_, quality=qualite)
		mime = "image/jpeg" if format_ == "JPEG" else "image/png"
		self.j["images"].append({"bufferView": self._vue(tampon.getvalue()), "mimeType": mime, "name": nom})
		self.j["textures"].append({"sampler": 0, "source": len(self.j["images"]) - 1})
		return len(self.j["textures"]) - 1

	def materiau(self, nom, calque, qualite=88, **reglages):
		"""Couleur et métal/rugosité tirés d'un Calque (son masque de dorure)."""
		couleur = self._image(nom, calque.img, "JPEG", qualite)
		mr = self._image(nom + "_metal", calque.materiau(**reglages).resize((calque.w // 2, calque.h // 2)), "JPEG", 90)
		self.j["materials"].append({"name": nom, "pbrMetallicRoughness": {
			"baseColorTexture": {"index": couleur}, "metallicRoughnessTexture": {"index": mr},
			"metallicFactor": 1.0, "roughnessFactor": 1.0}})
		return len(self.j["materials"]) - 1


	def geometrie(self, m):
		pos = np.array(m.pos, np.float32)
		return {"POSITION": self._acces(pos, "VEC3", 5126, 34962, True),
			"NORMAL": self._acces(np.array(m.nrm, np.float32), "VEC3", 5126, 34962),
			"TEXCOORD_0": self._acces(np.array(m.uv, np.float32), "VEC2", 5126, 34962)}, \
			self._acces(np.array(m.idx, np.uint32), "SCALAR", 5125, 34963)

	def mesh(self, nom, geo, mat):
		attr, idx = geo
		self.j["meshes"].append({"name": nom, "primitives": [{"attributes": attr, "indices": idx, "material": mat}]})
		return len(self.j["meshes"]) - 1

	def noeud(self, nom, mesh=None, t=None, r=None, parent=None):
		n = {"name": nom}
		if mesh is not None:
			n["mesh"] = mesh
		if t is not None:
			n["translation"] = [float(v) for v in t]
		if r is not None:
			n["rotation"] = [float(v) for v in r]
		self.j["nodes"].append(n)
		i = len(self.j["nodes"]) - 1
		if parent is None:
			self.j["scenes"][0]["nodes"].append(i)
		else:
			self.j["nodes"][parent].setdefault("children", []).append(i)
		return i

	def ecrire(self, chemin):
		while len(self.bin) % 4:
			self.bin.append(0)
		self.j["buffers"] = [{"byteLength": len(self.bin)}]
		js = json.dumps(self.j, separators=(",", ":")).encode()
		js += b" " * (-len(js) % 4)
		with open(chemin, "wb") as f:
			f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(self.bin)))
			f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
			f.write(struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin))


def quat_x(deg):
	a = math.radians(deg) / 2
	return (math.sin(a), 0.0, 0.0, math.cos(a))


def quat_y(deg):
	a = math.radians(deg) / 2
	return (0.0, math.sin(a), 0.0, math.cos(a))




# --------------------------------------------------------------------------- assemblage

REGLAGES_BOOSTER = {"metal_mat": 0.05, "rugo_mat": 0.42, "metal_dore": 0.6, "rugo_dore": 0.28}
REGLAGES_BOITE = {"metal_mat": 0.0, "rugo_mat": 0.6, "metal_dore": 0.5, "rugo_dore": 0.3}
EDITIONS = tuple(da.EDITIONS)


def booster_edition(calque, serie, edition):
	"""Les boosters 1st Edition portent la pastille, comme les vrais ; les Reprint rien."""
	if edition != "first_edition":
		return calque
	c = da.Calque(calque.w, calque.h)
	c.img, c.dorure = calque.img.copy(), calque.dorure.copy()
	w = calque.w // 2   # la face avant occupe la moitié gauche de l'atlas
	fx, fy, fr = da.EDITION_BOOSTER
	da.mention_edition(c, serie, edition, w * fx, calque.h * fy, calque.h * fr)
	return c


def reduire(calque, facteur=2):
	"""Texture plus petite pour les boosters rangés dans un display."""
	c = da.Calque(calque.w // facteur, calque.h // facteur)
	c.img = calque.img.resize(c.img.size, Image.LANCZOS)
	c.dorure = calque.dorure.resize(c.img.size, Image.LANCZOS)
	return c


def noms_fichiers():
	"""Les 16 modèles d'une série, sans l'extension."""
	noms = ["booster_%d_%s" % (n, e) for e in EDITIONS for n in range(1, 5)]
	noms += ["%s_%s_%s" % (t, o, e) for t in ("demi_display", "display") for e in EDITIONS for o in ("ferme", "ouvert")]
	return noms


def generer_serie(cle, serie, journal=print):
	"""Écrit les 16 modèles d'une série dans Contenu/Scelle/Modeles/<id>/."""
	code = chemins.sealed()["series"][cle]["code"]
	dossier = chemins.modeles(cle)
	os.makedirs(dossier, exist_ok=True)
	for ancien in os.listdir(dossier):
		if ancien.endswith(".glb"):
			os.remove(os.path.join(dossier, ancien))
	geo_booster = maillage_booster()
	bases = [da.booster(cle, serie, n, code, SERTI / BOOSTER_H) for n in range(4)]
	textures = {ed: [booster_edition(t, serie, ed) for t in bases] for ed in EDITIONS}
	petites = {ed: [reduire(t) for t in textures[ed]] for ed in EDITIONS}
	fichiers = []

	for edition in EDITIONS:
		for n, tex in enumerate(textures[edition]):
			g = Gltf()
			mat = g.materiau("booster_%d" % (n + 1), tex, **REGLAGES_BOOSTER)
			g.noeud("Booster", g.mesh("booster", g.geometrie(geo_booster), mat))
			chemin = os.path.join(dossier, "booster_%d_%s.glb" % (n + 1, edition))
			g.ecrire(chemin)
			fichiers.append(chemin)

	for nombre, nom in ((12, "demi_display"), (24, "display")):
		a = atlas_display(cle, serie, code, nombre)
		L, P, H, rangs = dims_display(nombre)
		for edition in EDITIONS:
			boite = avec_edition(a, serie, edition)
			for ouvert in (False, True):
				g = Gltf()
				mat_boite = g.materiau("boite", boite, qualite=90, **REGLAGES_BOITE)
				corps, volet = maillage_display(a, nombre, ouvert)
				racine = g.noeud("Display" if nombre == 24 else "DemiDisplay")
				g.noeud("Boite", g.mesh("boite", g.geometrie(corps), mat_boite), parent=racine)
				if ouvert:
					g.noeud("Couvercle", g.mesh("couvercle", g.geometrie(volet), mat_boite),
						t=(0, H, -P / 2), r=quat_x(-14), parent=racine)
					geo = g.geometrie(geo_booster)
					mats = [g.materiau("booster_%d" % (n + 1), t, qualite=85, **REGLAGES_BOOSTER) for n, t in enumerate(petites[edition])]
					meshes = [g.mesh("booster_%d" % (n + 1), geo, mats[n]) for n in range(4)]
					rng = np.random.default_rng(len(cle) * 31 + nombre)
					avant = P / 2 - PAROI - 0.001 - PAS / 2
					for col, x in enumerate((-(BOOSTER_L / 2 + 0.001), BOOSTER_L / 2 + 0.001)):
						for r in range(rangs):
							n = (r + 2 * col) % 4
							g.noeud("Booster_%d_%02d" % (col + 1, r + 1), meshes[n],
								t=(x + rng.uniform(-0.0006, 0.0006), PAROI + rng.uniform(0, 0.0015), avant - r * PAS),
								r=quat_y(rng.uniform(-1.2, 1.2)), parent=racine)
				chemin = os.path.join(dossier, "%s_%s_%s.glb" % (nom, "ouvert" if ouvert else "ferme", edition))
				g.ecrire(chemin)
				fichiers.append(chemin)
	for f in fichiers:
		journal("%7.0f Ko  %s" % (os.path.getsize(f) / 1024, chemins.relatif(f)))
	return fichiers


def ecrire_apercu(series):
	"""Apercu.tscn : une rangée par série, les boosters puis les displays de chaque édition."""
	res, noeuds = [], []
	for s, cle in enumerate(series):
		x = 0.0
		for nom in noms_fichiers():
			f = os.path.join(chemins.modeles(cle), nom + ".glb")
			if not os.path.exists(f):
				continue
			res.append('[ext_resource type="PackedScene" path="res://%s" id="%d"]' % (chemins.relatif(f), len(res) + 1))
			noeuds.append('[node name="%s_%s" parent="." instance=ExtResource("%d")]\ntransform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, %.3f, 0, %.2f)' % (cle, nom, len(res), x, -0.35 * s))
			x += 0.11 if nom.startswith("booster") else 0.2
	scene = """[gd_scene load_steps=%d format=3]

%s

[sub_resource type="ProceduralSkyMaterial" id="ProceduralSkyMaterial_1"]

[sub_resource type="Sky" id="Sky_1"]
sky_material = SubResource("ProceduralSkyMaterial_1")

[sub_resource type="Environment" id="Environment_1"]
background_mode = 2
sky = SubResource("Sky_1")
tonemap_mode = 2

[node name="ApercuScelle" type="Node3D"]

[node name="WorldEnvironment" type="WorldEnvironment" parent="."]
environment = SubResource("Environment_1")

[node name="Soleil" type="DirectionalLight3D" parent="."]
transform = Transform3D(0.866025, -0.321394, 0.383022, 0, 0.766044, 0.642788, -0.5, -0.55667, 0.663414, 0, 1, 0)

[node name="Camera3D" type="Camera3D" parent="."]
transform = Transform3D(1, 0, 0, 0, 0.77, 0.64, 0, -0.64, 0.77, 1.25, 1.3, 1.0)
fov = 45.0

%s
""" % (len(res) + 4, "\n".join(res), "\n\n".join(noeuds))
	with open(chemins.scelle("Apercu.tscn"), "w", encoding="utf-8") as f:
		f.write(scene)
