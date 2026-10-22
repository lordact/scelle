"""Le détourage des monstres, et sa note de qualité.

Deux moteurs :
  - rembg (u2net, isnet-general-use), pour de vrai : il demande rembg,
    onnxruntime et scipy (pip install rembg onnxruntime scipy) ;
  - simple : retire la couleur du fond, estimée sur les bords. Il ne sert qu'aux
    tests et aux illustrations sur fond uni.

Le masque est nettoyé (îlots parasites retirés, trous bouchés, bord adouci) et
fondu là où le monstre touche le bord de l'illustration, pour ne jamais
montrer une coupe droite. La qualité (0 à 1) sert à choisir les monstres d'une
nouvelle série et le modèle de détourage qui leur va le mieux.
"""
import os

import numpy as np
from PIL import Image, ImageFilter

FONDU = 0.10   # part de la taille sur laquelle un bord coupé s'efface
MODELES = ("isnet-general-use", "u2net")
_sessions = {}


def _composantes(plein):
	"""Étiquettes des zones connexes (scipy si présent, sinon un remplissage simple)."""
	try:
		from scipy import ndimage
		return ndimage.label(plein)
	except ImportError:
		h, w = plein.shape
		etiquettes = np.zeros((h, w), int)
		n = 0
		for y0, x0 in zip(*np.nonzero(plein)):
			if etiquettes[y0, x0]:
				continue
			n += 1
			pile = [(y0, x0)]
			etiquettes[y0, x0] = n
			while pile:
				y, x = pile.pop()
				for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
					if 0 <= yy < h and 0 <= xx < w and plein[yy, xx] and not etiquettes[yy, xx]:
						etiquettes[yy, xx] = n
						pile.append((yy, xx))
		return etiquettes, n


def nettoyer(alpha):
	plein = alpha > 128
	petit = np.asarray(Image.fromarray(plein.astype(np.uint8) * 255).resize((max(1, plein.shape[1] // 4), max(1, plein.shape[0] // 4)))) > 127
	etiquettes, n = _composantes(petit)
	if n == 0:
		return alpha
	aires = np.bincount(etiquettes.ravel())[1:]
	garder = np.isin(etiquettes, 1 + np.flatnonzero(aires >= aires.max() * 0.12))
	garder = Image.fromarray(garder.astype(np.uint8) * 255).resize((plein.shape[1], plein.shape[0]))
	garder = garder.filter(ImageFilter.MaxFilter(7))
	try:
		from scipy import ndimage
		garder = ndimage.binary_fill_holes(np.asarray(garder) > 127)
	except ImportError:
		garder = np.asarray(garder) > 127
	a = alpha.astype(float) * garder
	return np.asarray(Image.fromarray(a.astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8)), float)


def fondre_bords(a):
	"""Efface en douceur le monstre là où l'illustration le coupe."""
	h, w = a.shape
	plein = a > 128
	for cote, bande in (("haut", plein[:3]), ("bas", plein[-3:]), ("gauche", plein[:, :3]), ("droite", plein[:, -3:])):
		if bande.sum() < 12:
			continue
		if cote in ("haut", "bas"):
			n = int(h * FONDU)
			r = np.clip(np.arange(h) / n, 0, 1) if cote == "haut" else np.clip((h - 1 - np.arange(h)) / n, 0, 1)
			a *= (r ** 1.5)[:, None]
		else:
			n = int(w * FONDU)
			r = np.clip(np.arange(w) / n, 0, 1) if cote == "gauche" else np.clip((w - 1 - np.arange(w)) / n, 0, 1)
			a *= (r ** 1.5)[None, :]
	return a


def masque_rembg(im, modele):
	from rembg import new_session, remove
	if modele not in _sessions:
		_sessions[modele] = new_session(modele)
	return np.asarray(remove(im, session=_sessions[modele], only_mask=True, post_process_mask=True), float)


def masque_simple(im):
	"""Le fond est la couleur médiane des bords ; tout ce qui s'en écarte est le monstre."""
	a = np.asarray(im, float)
	bords = np.concatenate([a[:4].reshape(-1, 3), a[-4:].reshape(-1, 3), a[:, :4].reshape(-1, 3), a[:, -4:].reshape(-1, 3)])
	fond = np.median(bords, axis=0)
	d = np.sqrt(((a - fond) ** 2).sum(axis=2))
	return np.clip((d - 30) * 6, 0, 255)


def masque(im, moteur="rembg", modele=MODELES[0]):
	"""Le masque nettoyé du monstre, à la taille de l'illustration (0 à 255)."""
	im = im.convert("RGB")
	return nettoyer(masque_rembg(im, modele) if moteur == "rembg" else masque_simple(im))


def decouper(im, alpha):
	"""RGBA du monstre, bords coupés fondus, recadré sur lui."""
	rgba = im.convert("RGB").copy()
	rgba.putalpha(Image.fromarray(np.clip(fondre_bords(alpha.copy()), 0, 255).astype(np.uint8)))
	boite = rgba.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
	if boite:
		rgba = rgba.crop(boite)
	rgba.thumbnail((1100, 1100), Image.LANCZOS)
	return rgba


def detourer(im, moteur="rembg", modele=MODELES[0]):
	"""RGBA du monstre, recadré sur lui."""
	return decouper(im, masque(im, moteur, modele))


def qualite(rgba, taille_source):
	"""Note de 0 à 1 d'un détourage : un monstre net, d'un seul tenant, ni minuscule
	ni confondu avec tout le décor, et peu coupé par les bords de l'illustration."""
	a = np.asarray(rgba.getchannel("A").resize((128, max(1, int(128 * rgba.height / max(1, rgba.width))))), float) / 255
	plein = a > 0.5
	if plein.sum() < 50:
		return 0.0
	w0, h0 = taille_source
	part = (rgba.width * rgba.height * plein.mean()) / float(w0 * h0)   # part de l'illustration
	note_part = 1.0 if 0.08 <= part <= 0.55 else max(0.0, 1 - abs(part - (0.08 if part < 0.08 else 0.55)) * 4)
	etiquettes, n = _composantes(plein)
	aires = np.bincount(etiquettes.ravel())[1:]
	note_bloc = aires.max() / aires.sum() if n else 0
	solidite = plein.mean()                                   # remplissage de son cadre
	note_solide = min(1.0, solidite / 0.35)
	flou = ((a > 0.1) & (a < 0.9)).mean() / max(1e-3, (a > 0.1).mean())   # bord incertain
	note_net = max(0.0, 1 - flou * 2.5)
	return float(round(note_part * note_bloc * note_solide * note_net, 3))


def accord(a, b):
	"""Part commune de deux masques (0 à 1) : deux modèles qui détourent la même
	forme se trompent rarement ensemble."""
	a, b = a > 128, b > 128
	return float((a & b).sum() / max(1, (a | b).sum()))


def detourer_fichier(source, sortie, moteur="rembg", modeles=MODELES):
	"""Détoure une illustration avec chaque modèle et garde le meilleur.

	La note finale est la qualité du meilleur détourage pondérée par l'accord
	entre les modèles : un monstre que les deux modèles voient différemment (l'un
	prend le sol avec, l'autre en oublie la moitié) passe derrière les autres.
	Rend (modèle retenu, note, accord)."""
	im = Image.open(source).convert("RGB")
	essais = []
	for modele in (modeles if moteur == "rembg" else ("simple",)):
		alpha = masque(im, moteur, modele)
		rgba = decouper(im, alpha)
		essais.append((qualite(rgba, im.size), modele, alpha, rgba))
	q, modele, alpha, rgba = max(essais, key=lambda e: e[0])
	entente = min(accord(alpha, e[2]) for e in essais) if len(essais) > 1 else 1.0
	note = round(q * (0.4 + 0.6 * entente), 3)
	os.makedirs(os.path.dirname(sortie), exist_ok=True)
	rgba.save(sortie, "WEBP", quality=90, method=6)
	return modele, note, round(entente, 2)
