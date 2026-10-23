"""Les séries : leur fiche de direction artistique, et sa création automatique.

Une fiche (Contenu/Scelle/Series/<id>.json) dit tout ce qu'il faut pour
fabriquer le scellé d'une série :

    style        mythic | mecha | cosmic
    logo         [ligne 1, ligne 2] (ligne 2 vide : logo d'une ligne)
    police       serif | ronde
    fond, accent, accent2, encre, interieur : couleurs (hexadécimal)
    heros        les 4 monstres des boosters, dans l'ordre, puis des displays
    figurants    les monstres des côtés, du couvercle, de l'en-tête et du dos
    candidats    (fiche automatique) tous les monstres détourés et leur note

Pour une nouvelle série, creer() remplit tout seul la fiche à partir de
CardForge (serie.json et les illustrations) et de sealed.json (nom, code) :
style et modèle de détourage selon le genre des illustrations, palette tirée
des illustrations, monstres choisis sur la qualité du détourage et la variété
des couleurs. La fiche reste modifiable à la main.
"""
import colorsys
import glob
import json
import os

import numpy as np
from PIL import Image

import chemins
import detourage
import visuels

COULEURS = ("fond", "accent", "accent2", "encre", "interieur")
N_HEROS, N_FIGURANTS = 4, 5


# --------------------------------------------------------------------------- fiches

def lire(cle):
	with open(chemins.fiche(cle), encoding="utf-8") as f:
		fiche = json.load(f)
	fiche["logo"] = tuple(fiche["logo"])
	return fiche


def ecrire(cle, fiche):
	os.makedirs(os.path.dirname(chemins.fiche(cle)), exist_ok=True)
	donnees = dict(fiche)
	donnees["logo"] = list(donnees["logo"])
	with open(chemins.fiche(cle), "w", encoding="utf-8") as f:
		json.dump(donnees, f, indent="\t", ensure_ascii=False)
		f.write("\n")


def toutes():
	"""Les fiches présentes, dans l'ordre des séries de sealed.json."""
	ordre = list(chemins.sealed().get("series", {}))
	cles = [os.path.basename(p)[:-5] for p in glob.glob(chemins.scelle("Series", "*.json"))]
	cles.sort(key=lambda c: (ordre.index(c) if c in ordre else len(ordre), c))
	return {c: lire(c) for c in cles}


def sans_fiche():
	"""Les séries de sealed.json qui n'ont pas encore de scellé."""
	return [c for c in chemins.sealed().get("series", {}) if not os.path.exists(chemins.fiche(c))]


def verifier_fiche(cle, fiche):
	erreurs = []
	if fiche.get("style") not in ("mythic", "mecha", "cosmic"):
		erreurs.append("style inconnu : %s" % fiche.get("style"))
	for k in COULEURS:
		v = str(fiche.get(k, ""))
		if len(v) != 6 or any(c not in "0123456789abcdefABCDEF" for c in v):
			erreurs.append("couleur %s invalide : %r" % (k, v))
	if len(fiche.get("heros", [])) != N_HEROS:
		erreurs.append("il faut %d héros (un par booster)" % N_HEROS)
	if not fiche.get("figurants"):
		erreurs.append("il faut au moins un figurant")
	for m in fiche.get("heros", []) + fiche.get("figurants", []):
		if not os.path.exists(chemins.jeu(m["art"])):
			erreurs.append("illustration absente : %s" % m["art"])
	return ["%s : %s" % (cle, e) for e in erreurs]


# --------------------------------------------------------------------------- découverte

def illustrations(cle):
	"""Les illustrations de la série dans CardForge, une par créature : la Common si elle
	est déjà détourée (fond transparent : son contour est le bon, sans rembg), sinon
	l'Ultra de préférence.

	Format des nouvelles séries : CardForge/series/<id>/serie.json et ses images ;
	format historique (Mythic Origins) : CardForge/data/cards/*.json et
	CardForge/assets/illustrations/."""
	dossier = chemins.jeu("CardForge", "series", cle)
	trouvees = []
	if os.path.exists(os.path.join(dossier, "serie.json")):
		with open(os.path.join(dossier, "serie.json"), encoding="utf-8") as f:
			serie = json.load(f)
		cartes = serie.get("cards", [])
		for c in serie.get("creatures", []):
			images = {k.get("rarity"): k.get("image") for k in cartes if k.get("creature") == c["id"]}
			detourees = [n for n in (images.get("common"), "%s_base.webp" % c["id"])
				if n and os.path.exists(os.path.join(dossier, n)) and detourage.deja_detouree(os.path.join(dossier, n))]
			peintes = [n for n in (images.get("ultra"), "%s_ultra.webp" % c["id"], images.get("holo"), images.get("common"), "%s_base.webp" % c["id"])
				if n and os.path.exists(os.path.join(dossier, n))]
			if peintes:
				# "art": what the monster is cut from; "reference": the full illustration
				# (style and palette are judged on it, not on a cut-out's empty background).
				trouvees.append({"creature": c["id"], "art": chemins.relatif(os.path.join(dossier, (detourees or peintes)[0])),
					"reference": chemins.relatif(os.path.join(dossier, peintes[0]))})
		return trouvees, serie
	cartes = []
	for p in sorted(glob.glob(chemins.jeu("CardForge", "data", "cards", "*.json"))):
		with open(p, encoding="utf-8") as f:
			k = json.load(f)
		# une par créature : les Ultra Secrets reprennent la même illustration
		if k.get("set") == cle and k.get("rarity") == "ultra" and all(c["creature"] != k["creature"] for c in cartes):
			cartes.append(k)
	for k in cartes:
		for ext in (".webp", ".png", ".jpg"):
			p = chemins.jeu("CardForge", "assets", "illustrations", k["illustration"] + ext)
			if os.path.exists(p):
				trouvees.append({"creature": k["creature"], "art": chemins.relatif(p)})
				break
	meta = {}
	p = chemins.jeu("CardForge", "data", "sets", cle + ".json")
	if os.path.exists(p):
		with open(p, encoding="utf-8") as f:
			meta = json.load(f)
	return trouvees, meta


def logo_depuis_nom(nom):
	"""« Manga Mecha: Relic Protocol » -> (MANGA MECHA, RELIC PROTOCOL) ;
	« Cosmic Oddities » -> (COSMIC, ODDITIES) ; « Glitch » -> (GLITCH, "")."""
	if ":" in nom:
		a, b = nom.split(":", 1)
		return a.strip().upper(), b.strip().upper()
	mots = nom.upper().split()
	if len(mots) < 2:
		return (nom.upper().strip(), "")
	# la coupure qui équilibre le mieux les deux lignes, la première pas plus courte
	coupe = min(range(1, len(mots)), key=lambda i: abs(len(" ".join(mots[:i])) - len(" ".join(mots[i:]))))
	return " ".join(mots[:coupe]), " ".join(mots[coupe:])


# --------------------------------------------------------------------------- style et palette

def _petite(chemin, taille=(160, 224)):
	return Image.open(chemins.jeu(chemin)).convert("RGB").resize(taille)


def genre(arts):
	"""Le style qui va aux illustrations.

	Dessin animé (aplats : la moitié de l'image sans aucun dégradé) -> cosmic ;
	peu saturé (métal, béton, ciel gris) -> mecha ; peinture riche -> mythic.
	Mesures sur les séries d'origine : aplats 0,50 (Cosmic) contre moins de
	0,05 ; saturation 0,28 (Mecha) contre 0,47 (Mythic)."""
	plats, sats = [], []
	for a in arts:
		im = np.asarray(_petite(a), float)
		g = np.abs(np.diff(im, axis=1)).sum(2)[:-1, :] + np.abs(np.diff(im, axis=0)).sum(2)[:, :-1]
		plats.append((g < 6).mean())
		sats.append(np.asarray(_petite(a).convert("HSV"), float)[..., 1].mean() / 255)
	if np.median(plats) > 0.2:
		return "cosmic"
	return "mecha" if np.median(sats) < 0.36 else "mythic"


def _hex(r, g, b):
	return "%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def _hsv(h, s, v):
	return _hex(*colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v))))


def teintes(arts):
	"""Les teintes dominantes des illustrations (histogramme pondéré par la saturation)."""
	histo = np.zeros(36)
	for a in arts:
		hsv = np.asarray(_petite(a, (96, 134)).convert("HSV"), float) / 255
		h, s, v = hsv[..., 0].ravel(), hsv[..., 1].ravel(), hsv[..., 2].ravel()
		poids = s ** 2 * v
		np.add.at(histo, (h * 36).astype(int) % 36, poids)
	histo = np.convolve(np.concatenate([histo[-2:], histo, histo[:2]]), [1, 2, 3, 2, 1], "valid")
	ordre = np.argsort(histo)[::-1]
	retenues = []
	for i in ordre:
		h = (i + 0.5) / 36
		if all(min(abs(h - r), 1 - abs(h - r)) > 0.12 for r in retenues):
			retenues.append(h)
		if len(retenues) == 3:
			break
	while len(retenues) < 3:
		retenues.append((retenues[-1] + 0.33) % 1.0 if retenues else 0.6)
	return retenues


def palette(arts, style):
	"""fond, accent, accent2, encre, interieur, tirés des teintes des illustrations.

	Le fond prend la teinte dominante, très sombre ; l'accent la deuxième, vive
	(dorée pour le style mythic, comme une dorure à chaud) ; l'accent2 la
	troisième, claire."""
	h0, h1, h2 = teintes(arts)
	accent = _hsv(0.12, 0.65, 0.96) if style == "mythic" else _hsv(h1, 0.85, 1.0)
	accent2 = _hsv(0.13, 0.25, 1.0) if style == "mythic" else _hsv(h2, 0.55, 1.0)
	return {
		"fond": _hsv(h0, 0.6, 0.11 if style != "cosmic" else 0.28),
		"accent": accent,
		"accent2": accent2,
		"encre": _hsv(h0, 0.65, 0.07),
		"interieur": _hsv(h0, 0.6, 0.34),
	}


# --------------------------------------------------------------------------- choix des monstres

def _teinte_monstre(chemin):
	rgba = Image.open(chemin).convert("RGBA").resize((64, 64))
	a = np.asarray(rgba, float) / 255
	hsv = np.asarray(rgba.convert("RGB").convert("HSV"), float) / 255
	poids = a[..., 3] * hsv[..., 1] ** 2 * hsv[..., 2]
	if poids.sum() < 1e-3:
		return None
	ang = hsv[..., 0] * 2 * np.pi
	return float((np.arctan2((np.sin(ang) * poids).sum(), (np.cos(ang) * poids).sum()) / (2 * np.pi)) % 1.0)


def choisir(candidats, n_heros=N_HEROS, n_figurants=N_FIGURANTS):
	"""Les meilleurs détourages, en variant les couleurs : chaque nouveau choisi
	gagne des points s'il s'éloigne des teintes déjà prises."""
	restants = [c for c in candidats if c["qualite"] > 0]
	restants.sort(key=lambda c: -c["qualite"])
	pris = []
	while restants and len(pris) < n_heros + n_figurants:
		def note(c):
			if c.get("teinte") is None or not pris:
				return c["qualite"]
			ecart = min(min(abs(c["teinte"] - p["teinte"]), 1 - abs(c["teinte"] - p["teinte"])) for p in pris if p.get("teinte") is not None) if any(p.get("teinte") is not None for p in pris) else 0.5
			return c["qualite"] * (0.6 + 0.8 * min(ecart, 0.5))
		meilleur = max(restants, key=note)
		pris.append(meilleur)
		restants.remove(meilleur)
	if not pris:
		raise SystemExit("Aucun monstre détouré utilisable.")
	while len(pris) < n_heros + 1:   # série minuscule : on répète
		pris.append(pris[len(pris) % len(pris)])
	return pris[:n_heros], pris[n_heros:]


def creer(cle, moteur="rembg", style=None, journal=print):
	"""Crée la fiche d'une nouvelle série : détourage, style, palette, monstres."""
	sealed = chemins.sealed()["series"].get(cle)
	if sealed is None:
		raise SystemExit("%s n'est pas dans %s : l'ajouter d'abord à la boutique." % (cle, chemins.SEALED))
	trouvees, meta = illustrations(cle)
	if not trouvees:
		raise SystemExit("Aucune illustration trouvée pour %s dans CardForge." % cle)
	arts = [t["art"] for t in trouvees]
	# Style and palette from the full illustrations (the cut-out Commons have no background).
	reference = {t["art"]: t.get("reference", t["art"]) for t in trouvees}
	style = style or genre(list(reference.values()))
	journal("%s : %d illustrations, style %s" % (cle, len(arts), style))
	modeles = detourage.MODELES
	candidats = []
	for i, t in enumerate(trouvees):
		sortie = chemins.detourage(cle, visuels.nom_monstre(t))
		modele, q, entente = detourage.detourer_fichier(chemins.jeu(t["art"]), sortie, moteur, modeles)
		candidats.append({"art": t["art"], "modele": modele, "qualite": q, "accord": entente, "teinte": _teinte_monstre(sortie)})
		journal("  détouré %2d/%d  %-28s %-18s accord %.2f  note %.2f" % (i + 1, len(trouvees), t["creature"], modele, entente, q))
	heros, figurants = choisir(candidats)
	gardes = {visuels.nom_monstre(m) for m in heros + figurants}
	for c in candidats:   # seuls les détourages retenus restent dans le jeu
		if visuels.nom_monstre(c) not in gardes and os.path.exists(chemins.detourage(cle, visuels.nom_monstre(c))):
			os.remove(chemins.detourage(cle, visuels.nom_monstre(c)))
	logo = logo_depuis_nom(sealed.get("name", cle))
	fiche = {
		"auto": True,
		"style": style,
		"logo": logo,
		"police": "serif" if style == "mythic" else "ronde",
		**palette([reference[h["art"]] for h in heros] + [reference[f["art"]] for f in figurants], style),
		"heros": [{"art": h["art"], "modele": h["modele"]} for h in heros],
		"figurants": [{"art": f["art"], "modele": f["modele"]} for f in figurants],
		"candidats": sorted(candidats, key=lambda c: -c["qualite"]),
	}
	ecrire(cle, fiche)
	journal("Fiche écrite : %s" % chemins.relatif(chemins.fiche(cle)))
	return lire(cle)
