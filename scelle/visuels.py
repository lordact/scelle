"""Les visuels du scellé : boosters et displays, composés avec les monstres détourés.

Trois styles, au choix de chaque série (Series/<id>.json, clé « style ») :
  - mythic : grimoire nocturne, cercles d'or gravés, logo dorure à chaud,
    monstre auréolé d'un liseré d'or ;
  - mecha : plan technique et viseur tête haute, bandes de danger,
    logo chromé incliné, mecha avec traits de vitesse ;
  - cosmic : ciel étoilé de dessin animé, planètes, trame de points,
    logo bonbon qui rebondit, monstre en autocollant à gros contour blanc.

Chaque visuel est un Calque : l'image et son masque de dorure (les parties
métallisées : logo, bandes serties, liserés), qui devient la texture
métal/rugosité du modèle. La mise en page (Plan) garde chaque monstre en
entier, jamais sous un texte.
"""
import math
import os

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

import chemins

STYLES = ("mythic", "mecha", "cosmic")
POLICES = {
	"serif": "CardForge/assets/fonts/display/ArchiveSerif-Bold.ttf",
	"ronde": "addons/phantom_camera/fonts/Nunito-Black.ttf",
	"mono": "addons/gut/fonts/AnonymousPro-Bold.ttf",
}


def chemin_detourage(cle, monstre):
	return chemins.detourage(cle, nom_monstre(monstre))


def nom_monstre(m):
	nom = os.path.splitext(os.path.basename(m["art"]))[0]
	for fin in ("_ultra", "_base", "_holo"):
		if nom.endswith(fin):
			return nom[:-len(fin)]
	return nom


# --------------------------------------------------------------------------- outils

def rgb(h, a=None):
	c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
	return c if a is None else c + (a,)


def melange(c1, c2, t):
	return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def police(nom, taille):
	"""Les polices viennent du jeu ; sans elles, la police par défaut (tests)."""
	try:
		f = ImageFont.truetype(chemins.jeu(POLICES[nom]), max(6, int(taille)))
	except (OSError, SystemExit):
		return ImageFont.load_default(max(6, int(taille)))
	try:
		f.set_variation_by_axes([900])   # Nunito est une police variable : la graisse Black
	except OSError:
		pass
	return f


class Calque:
	"""Une image RGB et son masque de dorure (255 = métallisé)."""

	def __init__(self, w, h, fond=(0, 0, 0)):
		self.img = Image.new("RGB", (w, h), fond)
		self.dorure = Image.new("L", (w, h), 0)

	@property
	def w(self):
		return self.img.width

	@property
	def h(self):
		return self.img.height

	def coller(self, rgba, xy, dorure=None):
		x, y = int(xy[0]), int(xy[1])
		self.img.paste(rgba, (x, y), rgba)
		if dorure is not None:
			# ce qui recouvre efface la dorure dessous, puis on ajoute la sienne
			a = rgba.getchannel("A")
			calque = Image.new("L", self.dorure.size, 0)
			calque.paste(a, (x, y))
			self.dorure = ImageChops.multiply(self.dorure, ImageOps.invert(calque))
			if dorure is not False:
				d = Image.new("L", self.dorure.size, 0)
				d.paste(dorure, (x, y))
				self.dorure = ImageChops.lighter(self.dorure, d)

	def materiau(self, metal_dore=0.95, metal_mat=0.08, rugo_dore=0.22, rugo_mat=0.5):
		"""Texture métal/rugosité glTF : vert = rugosité, bleu = métal."""
		m = np.asarray(self.dorure, float) / 255
		g = (rugo_mat + (rugo_dore - rugo_mat) * m) * 255
		b = (metal_mat + (metal_dore - metal_mat) * m) * 255
		return Image.fromarray(np.dstack([np.zeros_like(g), g, b]).astype(np.uint8), "RGB")


def couleur_dominante(rgba):
	a = np.asarray(rgba.convert("RGBA").resize((96, 96)), float) / 255
	rgbv = a[..., :3]
	mx, mn = rgbv.max(axis=2), rgbv.min(axis=2)
	sat = (mx - mn) / np.maximum(mx, 1e-3)
	poids = a[..., 3] * sat ** 2 * mx
	if poids.sum() < 1e-3:
		return (200, 200, 200)
	c = (rgbv * poids[..., None]).sum(axis=(0, 1)) / poids.sum()
	c = c / max(c.max(), 1e-3)          # pleine luminosité
	return tuple(int(v * 255) for v in c)


def monstre(cle, m):
	return Image.open(chemin_detourage(cle, m)).convert("RGBA")


def ajuster(rgba, w, h):
	r = min(w / rgba.width, h / rgba.height)
	return rgba.resize((max(1, int(rgba.width * r)), max(1, int(rgba.height * r))), Image.LANCZOS)


def scene_floue(chemin, w, h, teinte, force=0.6, flou=0.025):
	art = Image.open(chemins.jeu(chemin)).convert("RGB")
	r = max(w / art.width, h / art.height)
	art = art.resize((math.ceil(art.width * r), math.ceil(art.height * r)), Image.LANCZOS)
	x, y = (art.width - w) // 2, (art.height - h) // 2
	art = art.crop((x, y, x + w, y + h)).filter(ImageFilter.GaussianBlur(max(w, h) * flou))
	return Image.blend(art, Image.new("RGB", (w, h), teinte), force)


def vignette(c, force=0.65):
	w, h = c.w, c.h
	y, x = np.mgrid[0:h, 0:w]
	d = np.sqrt(((x - w / 2) / (w / 2)) ** 2 + ((y - h / 2) / (h / 2)) ** 2) / math.sqrt(2)
	k = 1 - force * np.clip(d, 0, 1) ** 2
	c.img = Image.fromarray((np.asarray(c.img, float) * k[..., None]).astype(np.uint8), "RGB")


def halo(c, cx, cy, rayon, teinte, alpha=200):
	w, h = c.w, c.h
	y, x = np.mgrid[0:h, 0:w]
	d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / rayon
	a = np.clip(1 - d, 0, 1) ** 1.8 * alpha / 255
	base = np.asarray(c.img, float)
	col = np.array(teinte, float)
	c.img = Image.fromarray((base + (255 - base) * 0 + (col - base * 0.3) * a[..., None]).clip(0, 255).astype(np.uint8), "RGB")


def contour(rgba, epaisseur, teinte, flou=0):
	a = rgba.getchannel("A")
	pad = epaisseur + int(flou * 3) + 2
	grand = Image.new("L", (a.width + 2 * pad, a.height + 2 * pad), 0)
	grand.paste(a, (pad, pad))
	if epaisseur:
		grand = grand.filter(ImageFilter.MaxFilter(epaisseur * 2 + 1))
	if flou:
		grand = grand.filter(ImageFilter.GaussianBlur(flou))
	out = Image.new("RGBA", grand.size, teinte[:3] + (0,))
	out.putalpha(grand.point(lambda v: v * (teinte[3] if len(teinte) > 3 else 255) // 255))
	return out, pad


def poser_monstre(c, rgba, cx, bas, style, couleur, ombre=True):
	"""Pose un monstre détouré, centré en cx, les pieds en bas, avec son traitement."""
	x, y = cx - rgba.width / 2, bas - rgba.height
	e = max(3, rgba.width // 70)
	if style == "cosmic":
		lueur, p = contour(rgba, e * 4, couleur + (150,), flou=e * 3)
		c.coller(lueur, (x - p, y - p))
		ombre_, p = contour(rgba, e * 2, (0, 0, 0, 160), flou=e)
		c.coller(ombre_, (x - p + e * 2, y - p + e * 3))
		bord, p = contour(rgba, e * 2, (255, 255, 255, 255))
		c.coller(bord, (x - p, y - p))
	elif style == "mythic":
		lueur, p = contour(rgba, e * 3, couleur + (190,), flou=e * 6)
		c.coller(lueur, (x - p, y - p))
		lis, p = contour(rgba, max(2, e // 2), rgb("f4c45a", 255))
		c.coller(lis, (x - p, y - p), dorure=lis.getchannel("A"))
	else:
		lueur, p = contour(rgba, e * 2, couleur + (170,), flou=e * 5)
		c.coller(lueur, (x - p, y - p))
		lis, p = contour(rgba, max(2, e // 2), rgb("6fe3ff", 230))
		c.coller(lis, (x - p, y - p))
	c.coller(rgba, (x, y), dorure=False)


# --------------------------------------------------------------------------- motifs

def motif(c, serie, cx, cy, echelle, graine=1):
	style = serie["style"]
	rng = np.random.default_rng(graine)
	calque = Image.new("RGBA", c.img.size, (0, 0, 0, 0))
	d = ImageDraw.Draw(calque)
	ac = rgb(serie["accent"])
	if style == "mythic":
		dor = Image.new("L", c.img.size, 0)
		dd = ImageDraw.Draw(dor)
		for i, r in enumerate((0.92, 0.78, 0.62)):
			rr = r * echelle
			largeur = max(2, int(echelle * (0.012 if i == 0 else 0.006)))
			d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=ac + (150 - i * 30,), width=largeur)
			dd.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=200, width=largeur)
		for k in range(72):
			a = 2 * math.pi * k / 72
			r0, r1 = 0.92 * echelle, (0.86 if k % 6 else 0.80) * echelle
			d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a), cy + r1 * math.sin(a))], fill=ac + (130,), width=max(1, int(echelle * 0.005)))
		for k in range(12):
			a = 2 * math.pi * k / 12 + math.pi / 12
			px_, py_ = cx + 0.70 * echelle * math.cos(a), cy + 0.70 * echelle * math.sin(a)
			s = echelle * 0.025
			d.polygon([(px_, py_ - s), (px_ + s * 0.6, py_), (px_, py_ + s), (px_ - s * 0.6, py_)], fill=ac + (170,))
			dd.polygon([(px_, py_ - s), (px_ + s * 0.6, py_), (px_, py_ + s), (px_ - s * 0.6, py_)], fill=230)
		for k in range(16):   # rayons fins
			a = 2 * math.pi * k / 16
			d.line([(cx, cy), (cx + 2 * echelle * math.cos(a), cy + 2 * echelle * math.sin(a))], fill=ac + (22,), width=max(2, int(echelle * 0.03)))
		c.img.paste(calque, (0, 0), calque)
		c.dorure = ImageChops.lighter(c.dorure, dor)
		return
	if style == "mecha":
		pas = max(10, int(min(c.w, c.h) / 22))
		for x in range(0, c.w, pas):
			d.line([(x, 0), (x, c.h)], fill=rgb(serie["accent2"], 26 if (x // pas) % 4 else 55), width=1)
		for y in range(0, c.h, pas):
			d.line([(0, y), (c.w, y)], fill=rgb(serie["accent2"], 26 if (y // pas) % 4 else 55), width=1)
		for _ in range(26):    # traits de vitesse
			x0 = rng.uniform(-0.3, 1.1) * c.w
			y0 = rng.uniform(0, 1) * c.h
			lg = rng.uniform(0.2, 0.6) * c.w
			d.line([(x0, y0), (x0 + lg, y0 - lg * 0.35)], fill=(255, 255, 255, int(rng.uniform(18, 60))), width=int(rng.uniform(1, 4)))
		r = echelle * 0.85
		d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=rgb(serie["accent2"], 70), width=max(2, int(echelle * 0.008)))
		d.ellipse((cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55), outline=rgb(serie["accent2"], 45), width=max(1, int(echelle * 0.005)))
		for a in (0, 90, 180, 270):
			ra = math.radians(a)
			d.line([(cx + r * 0.9 * math.cos(ra), cy + r * 0.9 * math.sin(ra)), (cx + r * 1.15 * math.cos(ra), cy + r * 1.15 * math.sin(ra))], fill=rgb(serie["accent2"], 120), width=max(2, int(echelle * 0.01)))
		c.img.paste(calque, (0, 0), calque)
		return
	# cosmic
	for _ in range(int(c.w * c.h / 1800)):
		x, y = rng.uniform(0, c.w), rng.uniform(0, c.h)
		s = rng.choice([1, 1, 1, 2, 2, 3])
		d.ellipse((x - s, y - s, x + s, y + s), fill=(255, 255, 255, int(rng.uniform(90, 230))))
	for _ in range(max(3, int(c.w * c.h / 60000))):
		x, y = rng.uniform(0, c.w), rng.uniform(0, c.h)
		s = rng.uniform(0.012, 0.025) * max(c.w, c.h)
		d.polygon([(x, y - s), (x + s * 0.22, y - s * 0.22), (x + s, y), (x + s * 0.22, y + s * 0.22), (x, y + s), (x - s * 0.22, y + s * 0.22), (x - s, y), (x - s * 0.22, y - s * 0.22)], fill=(255, 250, 220, 230))
	planetes = [(0.12, 0.30, 0.10, serie["accent2"]), (0.9, 0.55, 0.07, serie["accent"]), (0.8, 0.12, 0.045, "ffd25a")]
	for px_, py_, r, col in planetes:
		x, y, rr = px_ * c.w, py_ * c.h, r * max(c.w, c.h)
		d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=rgb(col, 150))
		d.ellipse((x - rr * 0.55, y - rr * 0.75, x + rr * 0.1, y - rr * 0.2), fill=(255, 255, 255, 60))
		d.ellipse((x - rr * 1.7, y - rr * 0.35, x + rr * 1.7, y + rr * 0.35), outline=rgb(col, 170), width=max(2, int(rr * 0.12)))
	for y in range(0, c.h, 14):   # trame de points dans les coins
		for x in range(0, c.w, 14):
			k = max(0.0, 1 - math.hypot(x / c.w, (c.h - y) / c.h) * 2.2)
			if k > 0:
				s = 5 * k
				d.ellipse((x - s, y - s, x + s, y + s), fill=rgb(serie["accent2"], 70))
	c.img.paste(calque, (0, 0), calque)


# --------------------------------------------------------------------------- logo

def degrade_vertical(w, h, haut, bas, milieu=None):
	t = np.linspace(0, 1, h)[:, None]
	cols = []
	for k in range(3):
		if milieu:
			v = np.where(t < 0.5, haut[k] + (milieu[k] - haut[k]) * t * 2, milieu[k] + (bas[k] - milieu[k]) * (t - 0.5) * 2)
		else:
			v = haut[k] + (bas[k] - haut[k]) * t
		cols.append(np.repeat(v, w, axis=1))
	return Image.fromarray(np.dstack(cols).astype(np.uint8), "RGB")


def ligne_logo(texte_, taille, nom_police, largeur_max):
	f = police(nom_police, taille)
	while taille > 8 and f.getlength(texte_) > largeur_max:
		taille *= 0.94
		f = police(nom_police, taille)
	l, t, r, b = f.getbbox(texte_)
	m = Image.new("L", (r - l + 4, b - t + 4), 0)
	ImageDraw.Draw(m).text((2 - l, 2 - t), texte_, font=f, fill=255)
	return m


def logo(c, serie, cx, cy, largeur, hauteur):
	"""Le logo de la série, centré en (cx, cy), tenant dans largeur x hauteur."""
	img, dor = logo_rgba(serie, largeur, hauteur)
	c.coller(img, (cx - img.width / 2, cy - img.height / 2), dorure=dor)
	return img.size


def logo_rgba(serie, largeur, hauteur):
	"""Le logo rendu seul : l'image RGBA et son masque de dorure."""
	style = serie["style"]
	l1, l2 = serie["logo"]
	ratio2 = 0.62 if style != "cosmic" else 0.78
	if l2:
		m1 = ligne_logo(l1, hauteur * 0.55, serie["police"], largeur * 0.96)
		m2 = ligne_logo(l2, hauteur * 0.55 * ratio2, serie["police"], largeur * (0.92 if style == "mecha" else 0.8))
	else:   # nom de série d'un seul tenant : une seule ligne, plus grande
		m1 = ligne_logo(l1, hauteur * 0.8, serie["police"], largeur * 0.96)
		m2 = Image.new("L", (1, 1), 0)
	if style == "cosmic":
		m1 = m1.rotate(4, expand=True, resample=Image.BICUBIC)
		m2 = m2.rotate(-3, expand=True, resample=Image.BICUBIC)
	ecart = int(hauteur * (0.02 if style != "cosmic" else -0.04)) if l2 else 0
	w = max(m1.width, m2.width)
	masque = Image.new("L", (w, m1.height + m2.height + ecart), 0)
	masque.paste(m1, ((w - m1.width) // 2, 0))
	masque.paste(m2, ((w - m2.width) // 2, m1.height + ecart), m2)
	if style == "mecha":
		cis = 0.22
		masque = masque.transform((int(masque.width + masque.height * cis), masque.height), Image.AFFINE, (1, cis, -masque.height * cis, 0, 1, 0), resample=Image.BICUBIC)
	e = max(2, int(hauteur * 0.045))
	pad = e * 4
	M = Image.new("L", (masque.width + 2 * pad, masque.height + 2 * pad), 0)
	M.paste(masque, (pad, pad))
	W, H = M.size
	sortie = Image.new("RGBA", (W, H), (0, 0, 0, 0))
	encre = rgb(serie["encre"])
	contour_m = M.filter(ImageFilter.MaxFilter(e * 2 + 1))
	# relief : le contour répété vers le bas
	for k in range(e * 2, 0, -1):
		dec = Image.new("L", (W, H), 0)
		dec.paste(contour_m, (0, k))
		couche = Image.new("RGBA", (W, H), melange(encre, (0, 0, 0), 0.4) + (255,))
		couche.putalpha(dec)
		sortie = Image.alpha_composite(sortie, couche)
	lueur = Image.new("RGBA", (W, H), rgb(serie["accent"], 255))
	lueur.putalpha(contour_m.filter(ImageFilter.GaussianBlur(e * 2)).point(lambda v: v * 0.55))
	sortie = Image.alpha_composite(lueur, sortie)
	ct = Image.new("RGBA", (W, H), encre + (255,))
	ct.putalpha(contour_m)
	sortie = Image.alpha_composite(sortie, ct)
	if style == "mythic":
		rempl = degrade_vertical(W, H, rgb("fff6cf"), rgb("9a5a12"), rgb("f4c45a"))
	elif style == "mecha":
		rempl = degrade_vertical(W, H, rgb("ffffff"), rgb("8aa4bd"), rgb("dfe9f2"))
	else:
		rempl = degrade_vertical(W, H, rgb("fff27a"), rgb("ff5fae"), rgb("54f0d0"))
	plein = rempl.convert("RGBA")
	plein.putalpha(M)
	sortie = Image.alpha_composite(sortie, plein)
	# reflet en haut des lettres
	reflet = Image.new("RGBA", (W, H), (255, 255, 255, 0))
	haut = M.filter(ImageFilter.MinFilter(max(3, e | 1)))
	bande = Image.new("L", (W, H), 0)
	for y in range(H):
		bande.paste(int(110 * max(0, 1 - ((y % max(1, m1.height + pad)) / (m1.height * 0.45 + 1)))), (0, y, W, y + 1))
	reflet.putalpha(ImageChops.multiply(haut, bande))
	sortie = Image.alpha_composite(sortie, reflet)
	if style == "mecha":   # deuxième ligne en orange
		y2 = pad + m1.height + ecart
		orange = Image.new("RGBA", (W, H), rgb(serie["accent"], 255))
		m_bas = M.copy()
		ImageDraw.Draw(m_bas).rectangle((0, 0, W, y2 - 1), fill=0)
		orange.putalpha(m_bas)
		sortie = Image.alpha_composite(sortie, orange)
	r = min(largeur / W, hauteur / H) * 1.0
	sortie = sortie.resize((max(1, int(W * r)), max(1, int(H * r))), Image.LANCZOS)
	dor = M.resize(sortie.size, Image.LANCZOS) if style != "cosmic" else M.resize(sortie.size).point(lambda v: v * 0.5)
	return sortie, dor


def police_ajustee(s, taille, nom_police, largeur_max):
	f = police(nom_police, taille)
	while largeur_max and taille > 8 and f.getlength(s) > largeur_max:
		taille *= 0.94
		f = police(nom_police, taille)
	return f


def texte(c, xy, s, taille, fill, nom_police="ronde", ancre="mm", contour_=0, couleur_contour=(0, 0, 0), largeur_max=None):
	f = police_ajustee(s, taille, nom_police, largeur_max)
	ImageDraw.Draw(c.img).text(xy, s, font=f, fill=fill, anchor=ancre, stroke_width=contour_, stroke_fill=couleur_contour)


def bandeau(c, serie, cx, cy, largeur, hauteur, l1, l2=None):
	"""Le cartouche « BOOSTER PACK » propre à chaque série."""
	style = serie["style"]
	d = ImageDraw.Draw(c.img)
	dd = ImageDraw.Draw(c.dorure)
	x0, x1, y0, y1 = cx - largeur / 2, cx + largeur / 2, cy - hauteur / 2, cy + hauteur / 2
	encre = rgb(serie["encre"])
	if style == "mythic":
		pointe = hauteur * 0.5
		forme = [(x0, cy), (x0 + pointe, y0), (x1 - pointe, y0), (x1, cy), (x1 - pointe, y1), (x0 + pointe, y1)]
		d.polygon(forme, fill=rgb("f4c45a"), outline=encre, width=max(2, int(hauteur * 0.06)))
		dd.polygon(forme, fill=255)
		interne = [(x0 + pointe * 0.5, cy), (x0 + pointe * 1.1, y0 + hauteur * 0.16), (x1 - pointe * 1.1, y0 + hauteur * 0.16), (x1 - pointe * 0.5, cy), (x1 - pointe * 1.1, y1 - hauteur * 0.16), (x0 + pointe * 1.1, y1 - hauteur * 0.16)]
		d.polygon(interne, outline=melange(rgb("f4c45a"), encre, 0.5), width=max(1, int(hauteur * 0.03)))
		texte(c, (cx, cy if not l2 else cy - hauteur * 0.12), l1, hauteur * (0.42 if l2 else 0.5), encre, "serif", largeur_max=largeur - 2.6 * pointe)
		if l2:
			texte(c, (cx, cy + hauteur * 0.25), l2, hauteur * 0.26, encre, "serif", largeur_max=largeur - 2.6 * pointe)
	elif style == "mecha":
		cis = hauteur * 0.45
		forme = [(x0 + cis, y0), (x1, y0), (x1 - cis, y1), (x0, y1)]
		d.polygon(forme, fill=rgb(serie["accent"]))
		# bandes de danger à gauche
		for k in range(6):
			bx = x0 + cis + k * hauteur * 0.32
			d.polygon([(bx, y1 - hauteur * 0.18), (bx + hauteur * 0.16, y1 - hauteur * 0.18), (bx + hauteur * 0.16 - hauteur * 0.1, y1), (bx - hauteur * 0.1, y1)], fill=encre)
		texte(c, (cx, cy - (hauteur * 0.1 if l2 else 0)), l1, hauteur * (0.45 if l2 else 0.55), encre, "ronde", largeur_max=largeur - 2 * cis)
		if l2:
			texte(c, (cx + cis * 0.3, cy + hauteur * 0.26), l2, hauteur * 0.25, encre, "mono", largeur_max=largeur - 2 * cis)
	else:
		r = hauteur / 2
		d.rounded_rectangle((x0, y0 + hauteur * 0.08, x1, y1 + hauteur * 0.08), r, fill=melange(rgb(serie["accent2"]), (0, 0, 0), 0.45))
		d.rounded_rectangle((x0, y0, x1, y1), r, fill=rgb(serie["accent2"]), outline=(255, 255, 255), width=max(2, int(hauteur * 0.08)))
		d.ellipse((x0 + r * 0.4, y0 + hauteur * 0.15, x0 + r * 1.2, y0 + hauteur * 0.4), fill=(255, 255, 255))
		texte(c, (cx, cy - (hauteur * 0.1 if l2 else 0)), l1, hauteur * (0.45 if l2 else 0.55), (255, 255, 255), "ronde", contour_=max(2, int(hauteur * 0.06)), couleur_contour=encre, largeur_max=largeur - 2 * r)
		if l2:
			texte(c, (cx, cy + hauteur * 0.27), l2, hauteur * 0.25, encre, "ronde", largeur_max=largeur - 2 * r)


def serti(c, serie, y0, y1):
	"""Bande sertie métallisée, striée."""
	d = ImageDraw.Draw(c.img)
	base = np.array(rgb(serie["accent"] if serie["style"] != "mecha" else "b9c6d2"), float)
	for y in range(int(y0), int(y1)):
		k = 0.6 + 0.4 * math.sin(y * 1.9)
		d.line([(0, y), (c.w, y)], fill=tuple(int(min(255, v * k + 25)) for v in base))
	for x in range(0, c.w, 7):
		d.line([(x, y0), (x, y1)], fill=tuple(int(v * 0.55) for v in base), width=1)
	ImageDraw.Draw(c.dorure).rectangle((0, y0, c.w, y1), fill=255)


# --------------------------------------------------------------------------- mise en page

RAPPORT = []   # (panneau, monstre, échelle, part cachée par les textes) : la vérification


class Plan:
	"""Mise en page d'un panneau.

	Les textes (logo, cartouches, lignes, mentions) réservent d'abord leur place ;
	chaque monstre est ensuite posé là où il tient en entier, sans qu'aucun
	texte ne le recouvre : on cherche la plus grande taille possible, au plus
	près de sa place préférée, dans sa zone. Les monstres posés en premier sont
	dessinés devant. RAPPORT garde, pour chaque monstre, la part de lui
	cachée par un texte (0 attendu).
	"""
	F = 4   # résolution des masques de placement (1 case = 4 px)

	def __init__(self, c, serie, nom):
		self.c, self.serie, self.nom = c, serie, nom
		self.forme = (c.h // self.F + 1, c.w // self.F + 1)
		self.textes = np.zeros(self.forme, bool)
		self.monstres = np.zeros(self.forme, bool)
		self.dessins = []
		self.poses = []

	def _marquer(self, masque, x, y, petit):
		x, y = int(x // self.F), int(y // self.F)
		h, w = petit.shape
		x0, y0, x1, y1 = max(0, x), max(0, y), min(self.forme[1], x + w), min(self.forme[0], y + h)
		if x1 > x0 and y1 > y0:
			masque[y0:y1, x0:x1] |= petit[y0 - y:y1 - y, x0 - x:x1 - x]

	def _petit(self, alpha, marge):
		w, h = max(1, alpha.width // self.F), max(1, alpha.height // self.F)
		a = alpha.resize((w, h), Image.BILINEAR)
		if marge:
			a = a.filter(ImageFilter.MaxFilter(2 * marge + 1))
		return np.asarray(a) > 24

	def reserver(self, rect, dessin=None, marge=0.01):
		m = marge * min(self.c.w, self.c.h)
		x0, y0, x1, y1 = rect
		x0, y0 = int(max(0, x0 - m) // self.F), int(max(0, y0 - m) // self.F)
		x1, y1 = int((x1 + m) // self.F) + 1, int((y1 + m) // self.F) + 1
		self.textes[y0:y1, x0:x1] = True
		if dessin:
			self.dessins.append(dessin)

	def logo(self, cx, cy, largeur, hauteur):
		img, dor = logo_rgba(self.serie, largeur, hauteur)
		x, y = cx - img.width / 2, cy - img.height / 2
		self._marquer(self.textes, x - self.F * 2, y - self.F * 2, self._petit(img.getchannel("A"), 2))
		self.dessins.append(lambda: self.c.coller(img, (x, y), dorure=dor))
		return y + img.height

	def texte(self, xy, s, taille, fill, nom_police="ronde", ancre="mm", contour_=0, couleur_contour=(0, 0, 0), largeur_max=None):
		f = police_ajustee(s, taille, nom_police, largeur_max)
		boite = ImageDraw.Draw(self.c.img).textbbox(xy, s, font=f, anchor=ancre, stroke_width=contour_)
		self.reserver(boite, lambda: ImageDraw.Draw(self.c.img).text(xy, s, font=f, fill=fill, anchor=ancre, stroke_width=contour_, stroke_fill=couleur_contour), marge=0.006)

	def bandeau(self, cx, cy, largeur, hauteur, l1, l2=None):
		self.reserver((cx - largeur / 2, cy - hauteur / 2, cx + largeur / 2, cy + hauteur * 0.6),
			lambda: bandeau(self.c, self.serie, cx, cy, largeur, hauteur, l1, l2))

	def disque(self, cx, cy, r):
		"""La place d'une pastille posée après coup (mention d'édition), ombre comprise."""
		self.reserver((cx - r, cy - r, cx + r, cy + r * 1.15))

	def monstre(self, rgba, zone, cx, larg_max, haut_max, sur_monstres=0.12, nom="?", facultatif=False):
		"""Pose un monstre en entier dans zone (x0, y0, x1, y1), au plus près de cx.

		Un monstre facultatif qui ne tient pas aux deux tiers de sa taille n'est
		pas posé, plutôt que d'apparaître minuscule."""
		zx0, zy0, zx1, zy1 = zone
		base = ajuster(rgba, min(larg_max, zx1 - zx0), min(haut_max, zy1 - zy0))
		# d'abord posé au plus bas de sa zone (un peu plus haut au besoin) ; si rien
		# ne va à aucune taille, à n'importe quelle hauteur, sauf un monstre
		# facultatif : il reste au sol ou n'est pas posé
		passes = [(0.0, 0.04, 0.08, 0.12)] + ([] if facultatif else [tuple(np.arange(0.16, 1.0, 0.04))])
		meilleur = None
		for montees in passes:
			etat, pose = self._chercher(base, zone, cx, sur_monstres, facultatif, montees, nom)
			if etat == "pose":
				return pose
			if pose is not None and (meilleur is None or pose[0] < meilleur[0]):
				meilleur = pose
		if facultatif or meilleur is None:
			return None
		(cache, _), im, x, bas, petit, echelle = meilleur
		return self._poser(im, x, bas, petit, echelle, cache, nom)

	def _chercher(self, base, zone, cx, sur_monstres, facultatif, montees, nom):
		zx0, zy0, zx1, zy1 = zone
		marge = max(1, int(base.width / 70 * 3 / self.F))   # le contour et la lueur
		meilleur = None
		for echelle in np.arange(1.0, 0.64 if facultatif else 0.39, -0.04):
			im = base.resize((max(1, int(base.width * echelle)), max(1, int(base.height * echelle))), Image.LANCZOS)
			petit = self._petit(im.getchannel("A"), marge)
			total = max(1, petit.sum())
			xmin, xmax = zx0 + im.width / 2, zx1 - im.width / 2
			if xmin > xmax:
				continue
			pas = max(self.F, (xmax - xmin) / 40)
			xs = sorted(np.arange(xmin, xmax + 0.1, pas).tolist() + [min(max(cx, xmin), xmax)], key=lambda v: abs(v - cx))
			for montee in montees:
				bas = zy1 - montee * (zy1 - zy0)
				if bas - im.height < zy0:
					break
				for x in xs:
					px_, py_ = int((x - im.width / 2) // self.F), int((bas - im.height) // self.F)
					h, w = petit.shape
					sous_t = self.textes[py_:py_ + h, px_:px_ + w]
					sous_m = self.monstres[py_:py_ + h, px_:px_ + w]
					if sous_t.shape != petit.shape:
						continue
					cache = (sous_t & petit).sum() / total
					serre = (sous_m & petit).sum() / total
					if meilleur is None or (cache, serre) < meilleur[0]:
						meilleur = ((cache, serre), im, x, bas, petit, echelle)
					if cache == 0 and serre <= sur_monstres:
						return "pose", self._poser(im, x, bas, petit, echelle, 0.0, nom)
		return "rien", meilleur

	def _poser(self, im, x, bas, petit, echelle, cache, nom):
		self._marquer(self.monstres, x - im.width / 2, bas - im.height, petit)
		self.poses.append((im, x, bas))
		RAPPORT.append((self.nom, nom, float(echelle), float(cache)))
		return x, bas - im.height, im.width, im.height

	def dessiner(self):
		for im, x, bas in reversed(self.poses):
			poser_monstre(self.c, im, x, bas, self.serie["style"], couleur_dominante(im))
		for dessin in self.dessins:
			dessin()


# --------------------------------------------------------------------------- booster

BOOSTER_PX = (640, 1024)
EDITION_BOOSTER = (0.13, 0.765, 0.05)   # centre x, centre y (fractions de la face avant), rayon (de la hauteur)


def booster(cle, serie, n, code, serti_frac):
	"""Atlas du sachet : avant à gauche, dos à droite (1280 x 1024)."""
	W, H = BOOSTER_PX
	hs = int(H * serti_frac)
	heros = serie["heros"][n]
	bete = monstre(cle, heros)
	teinte = couleur_dominante(bete)
	fond = melange(rgb(serie["fond"]), teinte, 0.18)

	# Avant : logo en haut, cartouche en bas, la place de la pastille 1st Edition
	# réservée (même mise en page pour les deux éditions), le monstre en entier entre.
	av = Calque(W, H)
	av.img = scene_floue(heros["art"], W, H, fond, force=0.62 if serie["style"] != "cosmic" else 0.35)
	cy = int(H * 0.53)
	halo(av, W / 2, cy, W * 0.75, teinte, alpha=95 if serie["style"] == "mythic" else 150)
	motif(av, serie, W / 2, cy, W * 0.62, graine=n + 3)
	vignette(av, 0.55)
	p = Plan(av, serie, "booster %d avant" % (n + 1))
	p.logo(W / 2, H * 0.15, W * 0.9, H * 0.16)
	p.bandeau(W / 2, H * 0.875, W * 0.74, H * 0.07, "BOOSTER PACK", "10 CARDS · %s" % code)
	fx, fy, fr = EDITION_BOOSTER
	p.disque(W * fx, H * fy, H * fr)
	p.monstre(bete, (W * 0.03, hs + 4, W * 0.97, H * 0.835), W / 2, W * 0.94, H * 0.62, nom=nom_monstre(heros))
	p.dessiner()
	serti(av, serie, 0, hs)
	serti(av, serie, H - hs, H)

	# Dos
	dos = Calque(W, H)
	dos.img = scene_floue(heros["art"], W, H, rgb(serie["fond"]), force=0.82)
	motif(dos, serie, W / 2, H * 0.5, W * 0.5, graine=n + 11)
	vignette(dos, 0.4)
	p = Plan(dos, serie, "booster %d dos" % (n + 1))
	p.logo(W / 2, H * 0.14, W * 0.7, H * 0.12)
	encre_claire = rgb(serie["accent2"]) if serie["style"] != "mythic" else rgb("fff1c2")
	p.texte((W / 2, H * 0.27), "EACH PACK CONTAINS", 30, encre_claire)
	p.texte((W / 2, H * 0.32), "10 TRADING CARDS", 50, rgb(serie["accent"]), contour_=3, couleur_contour=rgb(serie["encre"]))
	for i, ligne in enumerate(("7 COMMON · 3 HOLO", "+ A CHANCE OF SECRET,", "ULTRA AND ULTRA SECRET")):
		p.texte((W / 2, H * 0.385 + i * 36), ligne, 26, (240, 240, 240))

	def code_barres():
		d = ImageDraw.Draw(dos.img)
		d.rectangle((50, H * 0.885, 250, H * 0.925), fill=(255, 255, 255))
		rng = np.random.default_rng(n)
		x = 56
		while x < 244:
			lw = int(rng.integers(1, 4))
			d.rectangle((x, H * 0.89, x + lw - 1, H * 0.918), fill=(0, 0, 0))
			x += lw + int(rng.integers(1, 4))
	p.reserver((50, H * 0.885, 250, H * 0.925), code_barres)
	p.texte((W - 60, H * 0.905), "%s-%d" % (code, n + 1), 22, (230, 230, 230), "mono", ancre="rm")
	p.monstre(bete, (W * 0.06, H * 0.47, W * 0.94, H * 0.875), W / 2, W * 0.7, H * 0.38, nom=nom_monstre(heros))
	p.dessiner()
	serti(dos, serie, 0, hs)
	serti(dos, serie, H - hs, H)

	atlas = Calque(W * 2, H)
	atlas.img.paste(av.img, (0, 0))
	atlas.img.paste(dos.img, (W, 0))
	atlas.dorure.paste(av.dorure, (0, 0))
	atlas.dorure.paste(dos.dorure, (W, 0))
	return atlas


# --------------------------------------------------------------------------- boîte
#
# Distribution des monstres sur une boîte, pour qu'aucun ne se répète sur les
# faces vues ensemble (façade, couvercle, côtés, en-tête) :
#   façade : héros 1 en vedette, héros 2 à droite, héros 3 à gauche
#   couvercle : figurant 1 ; côtés : figurants 2 et 3
#   en-tête : figurant 4 et héros 4 ; dos : héros 4 en vedette
#
# Le haut des faces (JUPE) passe sous la jupe du couvercle fermé : aucun
# monstre n'y va, pour qu'on le voie en entier boîte fermée.

EDITIONS = {"unlimited": "Reprint", "first_edition": "1st Edition"}
JUPE = 0.185


def figurant(serie, i):
	return serie["figurants"][i % len(serie["figurants"])]


def _fond_boite(cle, serie, w, h, heros, cx, cy, echelle, graine, force=None):
	bete = monstre(cle, heros)
	teinte = couleur_dominante(bete)
	if force is None:
		force = {"mythic": 0.6, "mecha": 0.75, "cosmic": 0.55}[serie["style"]]
	c = Calque(w, h)
	c.img = scene_floue(heros["art"], w, h, melange(rgb(serie["fond"]), teinte, 0.15), force=force)
	halo(c, cx, cy, echelle * 1.1, teinte, alpha=85 if serie["style"] == "mythic" else 140)
	motif(c, serie, cx, cy, echelle, graine=graine)
	vignette(c, 0.5)
	return c, bete, teinte


# où va la mention d'édition sur la façade (fractions de la largeur et de la hauteur)
EDITION_FACADE = (0.075, 0.79, 0.06)   # centre x, centre y, rayon (fraction de la hauteur)


def facade(cle, serie, code, w, h, nombre):
	"""Face avant : un monstre vedette, deux autres autour, le logo à gauche,
	le cartouche en bas et la place de la mention d'édition en bas à gauche."""
	h1, h2, h3 = serie["heros"][:3]
	c, bete, _ = _fond_boite(cle, serie, w, h, h1, w * 0.66, h * 0.58, h * 0.55, 21)
	p = Plan(c, serie, "façade %d" % nombre)
	p.logo(w * 0.29, h * 0.35, w * 0.54, h * 0.25)
	p.bandeau(w * 0.5, h * 0.935, w * 0.76, h * 0.09, "%d BOOSTER PACKS" % nombre, None)
	fx, fy, fr = EDITION_FACADE
	p.disque(w * fx, h * fy, h * fr)
	zone = (w * 0.015, h * JUPE, w * 0.985, h * 0.885)
	p.monstre(bete, zone, w * 0.76, w * 0.44, h * 0.7, nom=nom_monstre(h1))
	p.monstre(monstre(cle, h2), zone, w * 0.43, w * 0.24, h * 0.37, sur_monstres=0.03, nom=nom_monstre(h2))
	p.monstre(monstre(cle, h3), zone, w * 0.17, w * 0.22, h * 0.35, sur_monstres=0.03, nom=nom_monstre(h3))
	p.dessiner()
	return c


def mention_edition(c, serie, edition, cx, cy, r):
	"""Petite mention d'édition : pastille dorée « 1st Edition », étiquette « Reprint »."""
	d = ImageDraw.Draw(c.img)
	dd = ImageDraw.Draw(c.dorure)
	encre = rgb(serie["encre"])
	if edition == "first_edition":
		e = max(2, int(r * 0.12))
		d.ellipse((cx - r - e, cy - r - e + e, cx + r + e, cy + r + e + e), fill=(0, 0, 0))   # ombre
		d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rgb("f4c45a"))
		d.ellipse((cx - r + e, cy - r + e, cx + r - e, cy + r - e), fill=(18, 14, 12))
		dd.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
		dd.ellipse((cx - r + e, cy - r + e, cx + r - e, cy + r - e), fill=0)
		texte(c, (cx, cy - r * 0.18), "1ST", r * 0.78, rgb("f4c45a"), "ronde")
		texte(c, (cx, cy + r * 0.42), "EDITION", r * 0.3, rgb("f4c45a"), "ronde", largeur_max=r * 1.5)
	else:
		lw, lh = r * 2.3, r * 0.85
		e = max(2, int(lh * 0.1))
		d.rounded_rectangle((cx - lw / 2, cy - lh / 2 + e, cx + lw / 2, cy + lh / 2 + e), lh * 0.3, fill=(0, 0, 0))
		d.rounded_rectangle((cx - lw / 2, cy - lh / 2, cx + lw / 2, cy + lh / 2), lh * 0.3, fill=(236, 238, 240), outline=encre, width=e)
		texte(c, (cx, cy), "REPRINT", lh * 0.5, encre, "ronde", largeur_max=lw * 0.82)


EDITION_BANDE = (0.07, 0.56, 0.16)   # la même mention, sur la bande de la façade arrachée


def bande_ouverte(cle, serie, w, h, nombre):
	"""Ce qui reste de la façade quand on l'a arrachée pour présenter les boosters.

	Un panneau à part, et non le bas de la grande façade (qui coupait les
	monstres en deux sous le cartouche) : le bord prédécoupé en haut, le
	cartouche au centre, deux monstres en entier de part et d'autre, la place
	de la mention d'édition à gauche.
	"""
	h1, h2 = serie["heros"][0], serie["heros"][1]
	c, _, _ = _fond_boite(cle, serie, w, h, h1, w * 0.5, h * 0.6, w * 0.3, 71)
	p = Plan(c, serie, "bande %d" % nombre)
	p.bandeau(w * 0.5, h * 0.6, w * 0.5, h * 0.36, "%d BOOSTER PACKS" % nombre, None)
	fx, fy, fr = EDITION_BANDE
	p.disque(w * fx, h * fy, h * fr)
	haut = h * 0.12   # sous le bord prédécoupé
	p.monstre(monstre(cle, h1), (w * 0.74, haut, w * 0.99, h * 0.97), w * 0.87, w * 0.25, h * 0.85, nom=nom_monstre(h1))
	p.monstre(monstre(cle, h2), (w * 0.11, haut, w * 0.26, h * 0.97), w * 0.19, w * 0.15, h * 0.85, nom=nom_monstre(h2))
	p.dessiner()
	# bord prédécoupé : liseré en dents de scie
	d = ImageDraw.Draw(c.img)
	dent = max(4, int(h * 0.06))
	pts = [(x, dent if (x // dent) % 2 else 0) for x in range(0, w + dent, dent)]
	d.polygon([(0, 0)] + pts + [(w, 0)], fill=rgb(serie["interieur"]))
	d.line(pts, fill=melange(rgb(serie["interieur"]), (255, 255, 255), 0.35), width=max(1, dent // 3))
	return c


def dos(cle, serie, code, w, h, nombre):
	"""Face arrière : le 4e héros en vedette et le contenu de la boîte."""
	h4, fig = serie["heros"][3], figurant(serie, 4)
	c, bete, _ = _fond_boite(cle, serie, w, h, h4, w * 0.72, h * 0.58, h * 0.55, 24)
	p = Plan(c, serie, "dos %d" % nombre)
	p.logo(w * 0.27, h * 0.3, w * 0.46, h * 0.18)
	x0, y0, x1, y1 = w * 0.05, h * 0.43, w * 0.49, h * 0.84

	def encart():
		calque = Image.new("RGBA", c.img.size, (0, 0, 0, 0))
		ImageDraw.Draw(calque).rounded_rectangle((x0, y0, x1, y1), h * 0.03, fill=(0, 0, 0, 150), outline=rgb(serie["accent"], 200), width=max(2, int(h * 0.006)))
		c.img.paste(calque, (0, 0), calque)
		cx = (x0 + x1) / 2
		claire = rgb("fff1c2") if serie["style"] == "mythic" else rgb(serie["accent2"])
		texte(c, (cx, y0 + h * 0.05), "CONTENTS", h * 0.035, claire, "ronde")
		texte(c, (cx, y0 + h * 0.11), "%d BOOSTER PACKS" % nombre, h * 0.055, rgb(serie["accent"]), "ronde", largeur_max=(x1 - x0) * 0.9)
		texte(c, (cx, y0 + h * 0.17), "10 CARDS PER PACK", h * 0.035, (240, 240, 240), "ronde")
		for i, ligne in enumerate(("7 COMMON · 3 HOLO", "+ A CHANCE OF SECRET,", "ULTRA AND ULTRA SECRET")):
			texte(c, (cx, y0 + h * (0.23 + 0.04 * i)), ligne, h * 0.028, (220, 220, 220), "ronde", largeur_max=(x1 - x0) * 0.9)
		d = ImageDraw.Draw(c.img)
		bx0, by0 = x0 + w * 0.02, y1 - h * 0.075
		d.rectangle((bx0, by0, bx0 + w * 0.16, by0 + h * 0.055), fill=(255, 255, 255))
		rng = np.random.default_rng(len(code) + nombre)
		x = int(bx0) + 4
		while x < bx0 + w * 0.16 - 6:
			lw = int(rng.integers(1, 4))
			d.rectangle((x, by0 + 4, x + lw - 1, by0 + h * 0.055 - 5), fill=(0, 0, 0))
			x += lw + int(rng.integers(1, 4))
		texte(c, (x1 - w * 0.02, by0 + h * 0.027), "%s · AGES 6+" % code, h * 0.026, (230, 230, 230), "mono", ancre="rm")
	p.reserver((x0, y0, x1, y1), encart)
	p.bandeau(w * 0.5, h * 0.935, w * 0.76, h * 0.09, "%d BOOSTER PACKS" % nombre, None)
	zone = (w * 0.015, h * JUPE, w * 0.985, h * 0.885)
	p.monstre(bete, zone, w * 0.72, w * 0.44, h * 0.68, nom=nom_monstre(h4))
	p.monstre(monstre(cle, fig), zone, w * 0.94, w * 0.2, h * 0.36, sur_monstres=0.03, nom=nom_monstre(fig), facultatif=True)
	p.dessiner()
	return c


def cote(cle, serie, code, w, h, nombre, idx):
	fig = figurant(serie, 1 + idx)
	c, bete, _ = _fond_boite(cle, serie, w, h, fig, w * 0.5, h * 0.75, h * 0.4, 31 + idx)
	p = Plan(c, serie, "côté %d %d" % (nombre, idx + 1))
	p.logo(w * 0.5, h * 0.28, w * 0.9, h * 0.14)
	p.texte((w * 0.5, h * 0.43), str(nombre), h * 0.11, rgb(serie["accent"]), contour_=max(2, int(h * 0.01)), couleur_contour=rgb(serie["encre"]))
	p.texte((w * 0.5, h * 0.51), "BOOSTERS", h * 0.04, (245, 245, 245), contour_=max(1, int(h * 0.005)), couleur_contour=rgb(serie["encre"]), largeur_max=w * 0.8)
	p.texte((w * 0.5, h * 0.965), "%s · %d × 10 CARDS" % (code, nombre), h * 0.026, (235, 235, 235), "mono", largeur_max=w * 0.9)
	p.monstre(bete, (w * 0.04, h * JUPE, w * 0.96, h * 0.945), w * 0.5, w * 0.92, h * 0.42, nom=nom_monstre(fig))
	p.dessiner()
	return c


def dessus(cle, serie, w, h):
	fig = figurant(serie, 0)
	c, bete, _ = _fond_boite(cle, serie, w, h, fig, w * 0.22, h * 0.5, h * 0.6, 41)
	p = Plan(c, serie, "couvercle")
	p.logo(w * 0.65, h * 0.5, w * 0.58, h * 0.6)
	p.monstre(bete, (w * 0.03, h * 0.04, w * 0.97, h * 0.96), w * 0.2, w * 0.4, h * 0.92, nom=nom_monstre(fig))
	p.dessiner()
	return c


def entete(cle, serie, w, h):
	"""Face intérieure du couvercle relevé : l'en-tête du présentoir."""
	gauche, droite = figurant(serie, 3), serie["heros"][3]
	c, _, _ = _fond_boite(cle, serie, w, h, droite, w * 0.5, h * 0.9, w * 0.4, 51, force=0.7)
	p = Plan(c, serie, "en-tête")
	p.logo(w * 0.5, h * 0.4, w * 0.48, h * 0.58)
	p.bandeau(w * 0.5, h * 0.85, w * 0.44, h * 0.19, "BOOSTER PACKS")
	zone = (w * 0.01, h * 0.03, w * 0.99, h * 0.98)
	p.monstre(monstre(cle, droite), zone, w * 0.86, w * 0.26, h * 0.92, nom=nom_monstre(droite))
	p.monstre(monstre(cle, gauche), zone, w * 0.14, w * 0.26, h * 0.92, nom=nom_monstre(gauche))
	p.dessiner()
	return c


def jupe(serie, w, h):
	c = Calque(w, h, rgb(serie["fond"]))
	motif(c, serie, w / 2, h / 2, h * 2, graine=61)
	d = ImageDraw.Draw(c.img)
	d.rectangle((0, 0, w, max(2, h * 0.08)), fill=rgb(serie["accent"]))
	d.rectangle((0, h - max(2, h * 0.08), w, h), fill=rgb(serie["accent"]))
	ImageDraw.Draw(c.dorure).rectangle((0, 0, w, h * 0.08), fill=255)
	ImageDraw.Draw(c.dorure).rectangle((0, h - h * 0.08, w, h), fill=255)
	encre = rgb(serie["accent2"]) if serie["style"] != "mythic" else rgb(serie["accent"])
	texte(c, (w / 2, h / 2), "·  TRADING CARD GAME  ·  %s  ·" % " ".join(serie["logo"]), h * 0.4, encre, "ronde", largeur_max=w * 0.9)
	return c


def interieur(serie, w=64, h=64):
	"""Intérieur de la boîte : une couleur unie de la série, imprimée sur le carton."""
	return Calque(w, h, rgb(serie["interieur"]))
