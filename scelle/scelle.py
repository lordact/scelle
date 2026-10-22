#!/usr/bin/env python3
"""Le scellé du jeu (boosters, demi-displays de 12, displays de 24) en modèles 3D.

    python3 Contenu/Scelle/Outils/scelle.py                 # tout ce qui manque
    python3 Contenu/Scelle/Outils/scelle.py ajouter <série>  # une nouvelle série
    python3 Contenu/Scelle/Outils/scelle.py generer [séries] # refaire les modèles
    python3 Contenu/Scelle/Outils/scelle.py detourer <série> # refaire les détourages de la fiche
    python3 Contenu/Scelle/Outils/scelle.py verifier         # contrôle complet
    python3 Contenu/Scelle/Outils/scelle.py planches --godot <godot> [séries]

Sans commande : chaque série de sealed.json sans fiche est ajoutée
automatiquement (détourage, style, palette, choix des monstres), puis ses
16 modèles sont générés et vérifiés. Une série ajoutée à la boutique n'a donc
besoin que de cette commande.

Détourage : rembg (pip install rembg onnxruntime scipy) ; --moteur simple
s'en passe pour des illustrations sur fond uni.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chemins  # noqa: E402
import detourage  # noqa: E402
import modeles  # noqa: E402
import series  # noqa: E402
import verification  # noqa: E402
import visuels  # noqa: E402


def generer(cles, journal=print):
	fiches = series.toutes()
	erreurs = []
	for cle in cles:
		erreurs += series.verifier_fiche(cle, fiches[cle])
	if erreurs:
		raise SystemExit("Fiches à corriger :\n  " + "\n  ".join(erreurs))
	for cle in cles:
		journal("== %s" % cle)
		visuels.RAPPORT.clear()
		modeles.generer_serie(cle, fiches[cle], journal)
		if not mise_en_page(journal):
			raise SystemExit("%s : un texte recouvre un monstre (voir ci-dessus)." % cle)
	modeles.ecrire_apercu(list(fiches))


def mise_en_page(journal=print):
	"""Aucun monstre ne doit être recouvert par un texte."""
	caches = [r for r in visuels.RAPPORT if r[3] > 0]
	petits = [r for r in visuels.RAPPORT if r[2] < 0.6]
	journal("Mise en page : %d monstres posés, %d recouverts par un texte, %d réduits sous 60 %%."
		% (len(visuels.RAPPORT), len(caches), len(petits)))
	for panneau, nom, echelle, cache in caches + petits:
		journal("  %-20s %-18s échelle %.2f, caché %.1f %%" % (panneau, nom, echelle, cache * 100))
	return not caches


def boosters_attendus(nom):
	"""Les nœuds Booster d'un modèle : 1 pour un booster, 12 ou 24 dans un display ouvert."""
	if nom.startswith("booster_"):
		return 1
	if nom.startswith("demi_display_ouvert_"):
		return 12
	if nom.startswith("display_ouvert_"):
		return 24
	return 0


def verifier(journal=print):
	"""Chaque série de la boutique a sa fiche, ses détourages et ses 16 modèles valides."""
	problemes = []
	fiches = series.toutes()
	for cle in chemins.sealed().get("series", {}):
		if cle not in fiches:
			problemes.append("%s : pas de fiche (lancer scelle.py ajouter %s)" % (cle, cle))
			continue
		problemes += series.verifier_fiche(cle, fiches[cle])
		for m in fiches[cle]["heros"] + fiches[cle]["figurants"]:
			if not os.path.exists(visuels.chemin_detourage(cle, m)):
				problemes.append("%s : détourage absent pour %s" % (cle, visuels.nom_monstre(m)))
		for nom in modeles.noms_fichiers():
			f = os.path.join(chemins.modeles(cle), nom + ".glb")
			if not os.path.exists(f):
				problemes.append("%s : modèle absent %s" % (cle, nom))
				continue
			p, boosters = verification.verifier_glb(f)
			problemes += p
			attendu = boosters_attendus(nom)
			if boosters != attendu:
				problemes.append("%s : %d boosters dans %s, %d attendus" % (cle, boosters, nom, attendu))
	for p in problemes:
		journal("  " + p)
	journal("Vérification : %d séries, %s." % (len(fiches), "tout est bon" if not problemes else "%d problèmes" % len(problemes)))
	return not problemes


def detourer(cle, moteur, journal=print):
	fiche = series.lire(cle)
	for m in fiche["heros"] + fiche["figurants"]:
		modeles_ = (m["modele"],) if m.get("modele") and moteur == "rembg" else detourage.MODELES
		modele, q, _ = detourage.detourer_fichier(chemins.jeu(m["art"]), visuels.chemin_detourage(cle, m), moteur, modeles_)
		journal("  %-28s %-18s note %.2f" % (visuels.nom_monstre(m), modele, q))


def planches(cles, godot, sortie, journal=print):
	"""Rend chaque modèle dans Godot et assemble une planche par série (sortie/<série>.jpg)."""
	from PIL import Image, ImageDraw
	ici = os.path.dirname(os.path.abspath(__file__))
	os.makedirs(sortie, exist_ok=True)
	for cle in cles:
		with tempfile.TemporaryDirectory() as projet:
			with open(os.path.join(projet, "project.godot"), "w") as f:
				f.write('config_version=5\n[application]\nconfig/name="planches"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')
			shutil.copytree(chemins.modeles(cle), os.path.join(projet, "Modeles"))
			shutil.copy(os.path.join(ici, "rendu_planches.gd"), projet)
			subprocess.run([godot, "--headless", "--import", "--path", projet], capture_output=True, timeout=600)
			commande = [godot, "--path", projet, "--rendering-driver", "opengl3", "--resolution", "900x900", "-s", "rendu_planches.gd"]
			if shutil.which("xvfb-run") and not os.environ.get("DISPLAY"):
				commande = ["xvfb-run", "-a", "-s", "-screen 0 900x900x24"] + commande
			subprocess.run(commande, capture_output=True, timeout=900)
			T = 420
			noms = modeles.noms_fichiers()
			planche = Image.new("RGB", (4 * T, 4 * (T + 40) + 90), (24, 24, 28))
			d = ImageDraw.Draw(planche)
			d.text((20, 22), chemins.sealed()["series"][cle]["name"], font=visuels.police("ronde", 48), fill=(240, 240, 240))
			for i, nom in enumerate(noms):
				png = os.path.join(projet, "rendus", nom + ".png")
				if not os.path.exists(png):
					raise SystemExit("Godot n'a pas rendu %s (voir %s)" % (nom, godot))
				x, y = (i % 4) * T, 90 + (i // 4) * (T + 40)
				planche.paste(Image.open(png).convert("RGB").resize((T, T), Image.LANCZOS), (x, y))
				d.text((x + T / 2, y + T + 20), nom.replace("_", " "), font=visuels.police("ronde", 20), fill=(220, 220, 220), anchor="mm")
			chemin = os.path.join(sortie, cle + ".jpg")
			planche.save(chemin, quality=88)
			journal("Planche : %s" % chemin)


def main(argv=None):
	p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	p.add_argument("commande", nargs="?", default="auto", choices=("auto", "ajouter", "generer", "detourer", "verifier", "planches"))
	p.add_argument("series", nargs="*", help="ids de séries (sealed.json)")
	p.add_argument("--jeu", help="dossier du jeu (par défaut : celui qui contient ces outils)")
	p.add_argument("--moteur", default="rembg", choices=("rembg", "simple"), help="détourage")
	p.add_argument("--style", choices=visuels.STYLES, help="imposer le style d'une nouvelle série")
	p.add_argument("--remplacer", action="store_true", help="ajouter : refaire une fiche existante")
	p.add_argument("--godot", help="planches : l'exécutable Godot 4")
	p.add_argument("--sortie", default=os.path.join(tempfile.gettempdir(), "planches_scelle"), help="planches : dossier des images")
	a = p.parse_args(argv)
	if a.jeu:
		chemins.utiliser(a.jeu)
	chemins.racine()

	if a.commande == "auto":
		nouvelles = series.sans_fiche()
		for cle in nouvelles:
			series.creer(cle, a.moteur, a.style)
		manquantes = [c for c in series.toutes() if c in nouvelles or not all(
			os.path.exists(os.path.join(chemins.modeles(c), n + ".glb")) for n in modeles.noms_fichiers())]
		if manquantes:
			generer(manquantes)
		else:
			print("Rien à faire : chaque série a son scellé.")
		return 0 if verifier() else 1
	if a.commande == "ajouter":
		if not a.series:
			p.error("ajouter : donner l'id de la série")
		for cle in a.series:
			if os.path.exists(chemins.fiche(cle)) and not a.remplacer:
				raise SystemExit("%s a déjà une fiche (--remplacer pour la refaire)." % cle)
			series.creer(cle, a.moteur, a.style)
		generer(a.series)
		return 0 if verifier() else 1
	if a.commande == "generer":
		generer(a.series or list(series.toutes()))
		return 0 if verifier() else 1
	if a.commande == "detourer":
		for cle in a.series or list(series.toutes()):
			detourer(cle, a.moteur)
		return 0
	if a.commande == "verifier":
		return 0 if verifier() else 1
	if a.commande == "planches":
		if not a.godot:
			p.error("planches : donner --godot <exécutable Godot 4>")
		planches(a.series or list(series.toutes()), a.godot, a.sortie)
		return 0


if __name__ == "__main__":
	sys.exit(main())
