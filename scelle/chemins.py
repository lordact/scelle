"""Où sont les choses dans le jeu.

Le module travaille sur un projet Godot du jeu : par défaut celui qui contient
ces outils (on remonte jusqu'à project.godot), sinon celui donné par --jeu.
"""
import json
import os

SCELLE = os.path.join("Contenu", "Scelle")
SEALED = os.path.join("addons", "card_shop", "sealed.json")
RACINE = None


def trouver(depart):
	d = os.path.abspath(depart)
	while True:
		if os.path.exists(os.path.join(d, "project.godot")):
			return d
		parent = os.path.dirname(d)
		if parent == d:
			return None
		d = parent


def utiliser(racine):
	global RACINE
	if not racine or not os.path.exists(os.path.join(racine, "project.godot")):
		raise SystemExit("Pas de projet Godot du jeu ici : %s (donner --jeu <dossier du jeu>)" % racine)
	RACINE = os.path.abspath(racine)


def racine():
	if RACINE is None:
		utiliser(trouver(os.path.dirname(__file__)))
	return RACINE


def jeu(*chemin):
	return os.path.join(racine(), *chemin)


def scelle(*chemin):
	return jeu(SCELLE, *chemin)


def detourage(cle, nom):
	return scelle("Detourages", cle, nom + ".webp")


def modeles(cle):
	return scelle("Modeles", cle)


def fiche(cle):
	"""La direction artistique d'une série : Contenu/Scelle/Series/<id>.json."""
	return scelle("Series", cle + ".json")


def sealed():
	with open(jeu(SEALED), encoding="utf-8") as f:
		return json.load(f)


def relatif(chemin):
	return os.path.relpath(chemin, racine()).replace(os.sep, "/")
