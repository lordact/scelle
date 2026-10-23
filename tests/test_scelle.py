"""Tests du module scellé, sur un faux jeu monté pour l'occasion.

    python3 -m unittest discover -s tests -v

Le faux jeu a une série inventée de 7 créatures dessinées (des formes de
couleur sur fond uni), au format des nouvelles séries de CardForge : pas
besoin de rembg (moteur de détourage « simple ») ni des vraies illustrations.
"""
import io
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from PIL import Image, ImageDraw

ICI = os.path.dirname(os.path.abspath(__file__))
# le code est dans scelle/ (dépôt du module) ou juste au-dessus (dans le jeu, Contenu/Scelle/Outils/)
sys.path.insert(0, os.path.join(ICI, "..", "scelle") if os.path.isdir(os.path.join(ICI, "..", "scelle")) else os.path.join(ICI, ".."))

import chemins  # noqa: E402
import detourage  # noqa: E402
import modeles  # noqa: E402
import scelle  # noqa: E402
import series  # noqa: E402
import verification  # noqa: E402
import visuels  # noqa: E402

SERIE = "test_glitch"


def faux_jeu(dossier):
	"""Un projet de jeu minimal : sealed.json et une série CardForge de 7 créatures."""
	open(os.path.join(dossier, "project.godot"), "w").write("config_version=5\n")
	os.makedirs(os.path.join(dossier, "addons", "card_shop"))
	sealed = {"series": {SERIE: {"name": "Glitch Critters", "code": "GC1"}},
		"editions": {"unlimited": {"label": "Reprint"}, "first_edition": {"label": "1st Edition"}}}
	json.dump(sealed, open(os.path.join(dossier, "addons", "card_shop", "sealed.json"), "w"))
	d = os.path.join(dossier, "CardForge", "series", SERIE)
	os.makedirs(d)
	creatures, cartes = [], []
	for i in range(7):
		cid = "bestiole_%d" % i
		creatures.append({"id": cid, "name": "Bestiole %d" % i})
		cartes.append({"number": i + 1, "creature": cid, "rarity": "common", "image": cid + "_base.webp"})
		cartes.append({"number": 61 + i, "creature": cid, "rarity": "ultra", "image": cid + "_ultra.webp"})
		for fin in ("base", "ultra"):
			im = Image.new("RGB", (300, 420), (28, 30, 60))
			dr = ImageDraw.Draw(im)
			teinte = tuple(int(127 + 120 * math.cos(2 * math.pi * (i / 7 + k / 3))) for k in range(3))
			dr.ellipse((70, 120, 230, 330), fill=teinte, outline=(10, 10, 10), width=6)
			dr.polygon([(150, 40), (190, 140), (110, 140)], fill=teinte)
			dr.ellipse((115, 180, 140, 205), fill=(255, 255, 255))
			dr.ellipse((160, 180, 185, 205), fill=(255, 255, 255))
			im.save(os.path.join(d, "%s_%s.webp" % (cid, fin)))
	json.dump({"format": "cardforge_serie_v1", "id": SERIE, "name": "Glitch Critters", "code": "GC1",
		"creatures": creatures, "cards": cartes}, open(os.path.join(d, "serie.json"), "w"))


def lancer(*args):
	sortie = io.StringIO()
	with redirect_stdout(sortie):
		code = scelle.main(list(args))
	return code, sortie.getvalue()


class TestNoms(unittest.TestCase):
	def test_logo_depuis_nom(self):
		self.assertEqual(series.logo_depuis_nom("Manga Mecha: Relic Protocol"), ("MANGA MECHA", "RELIC PROTOCOL"))
		self.assertEqual(series.logo_depuis_nom("Cosmic Oddities"), ("COSMIC", "ODDITIES"))
		self.assertEqual(series.logo_depuis_nom("Glitch"), ("GLITCH", ""))
		l1, l2 = series.logo_depuis_nom("The Very Long Series Name")
		self.assertTrue(l1 and l2)

	def test_nom_monstre(self):
		self.assertEqual(visuels.nom_monstre({"art": "a/b/mecha_kenshi_ultra.webp"}), "mecha_kenshi")
		self.assertEqual(visuels.nom_monstre({"art": "a/b/glob_base.webp"}), "glob")


class TestSerieAutomatique(unittest.TestCase):
	"""Une nouvelle série, de bout en bout : fiche, détourages, 16 modèles valides."""

	@classmethod
	def setUpClass(cls):
		cls.jeu = tempfile.mkdtemp(prefix="scelle_test_")
		faux_jeu(cls.jeu)
		cls.code, cls.journal = lancer("--jeu", cls.jeu, "--moteur", "simple")

	@classmethod
	def tearDownClass(cls):
		shutil.rmtree(cls.jeu, ignore_errors=True)

	def test_commande_reussie(self):
		self.assertEqual(self.code, 0, self.journal)
		self.assertIn("tout est bon", self.journal)

	def test_illustrations_ultra(self):
		trouvees, _ = series.illustrations(SERIE)
		self.assertEqual(len(trouvees), 7)
		self.assertTrue(all(t["art"].endswith("_ultra.webp") for t in trouvees))

	def test_common_deja_detouree(self):
		# Une Common sur fond transparent est prise telle quelle, sans rembg.
		d = chemins.jeu("CardForge", "series", SERIE)
		base = os.path.join(d, "bestiole_0_base.webp")
		gardee = open(base, "rb").read()
		try:
			im = Image.new("RGBA", (300, 420), (0, 0, 0, 0))
			ImageDraw.Draw(im).ellipse((70, 120, 230, 330), fill=(200, 60, 60, 255))
			im.save(base)
			trouvees, _ = series.illustrations(SERIE)
			self.assertTrue(trouvees[0]["art"].endswith("bestiole_0_base.webp"))
			self.assertTrue(all(t["art"].endswith("_ultra.webp") for t in trouvees[1:]))
			sortie = os.path.join(self.jeu, "deja.webp")
			modele, note, accord = detourage.detourer_fichier(base, sortie)
			self.assertEqual((modele, accord), ("deja", 1.0))
			self.assertGreater(note, 0.5)
		finally:
			open(base, "wb").write(gardee)

	def test_fiche(self):
		fiche = series.lire(SERIE)
		self.assertEqual(series.verifier_fiche(SERIE, fiche), [])
		self.assertTrue(fiche["auto"])
		self.assertEqual(fiche["logo"], ("GLITCH", "CRITTERS"))
		self.assertEqual(fiche["style"], "cosmic")   # aplats : dessin animé
		self.assertEqual(len(fiche["heros"]), 4)
		noms = [visuels.nom_monstre(m) for m in fiche["heros"] + fiche["figurants"]]
		self.assertEqual(len(noms), len(set(noms)), "un monstre choisi deux fois")

	def test_seuls_les_detourages_retenus(self):
		fiche = series.lire(SERIE)
		gardes = {visuels.nom_monstre(m) + ".webp" for m in fiche["heros"] + fiche["figurants"]}
		self.assertEqual(set(os.listdir(chemins.scelle("Detourages", SERIE))), gardes)

	def test_seize_modeles_valides(self):
		for nom in modeles.noms_fichiers():
			chemin = os.path.join(chemins.modeles(SERIE), nom + ".glb")
			problemes, boosters = verification.verifier_glb(chemin)
			self.assertEqual(problemes, [], nom)
			self.assertEqual(boosters, scelle.boosters_attendus(nom), nom)

	def test_aucun_monstre_sous_un_texte(self):
		self.assertIn("0 recouverts par un texte", self.journal)

	def test_apercu(self):
		scene = open(chemins.scelle("Apercu.tscn"), encoding="utf-8").read()
		self.assertEqual(scene.count("instance=ExtResource"), 16)

	def test_relance_ne_refait_rien(self):
		code, journal = lancer("--jeu", self.jeu, "--moteur", "simple")
		self.assertEqual(code, 0, journal)
		self.assertIn("Rien à faire", journal)


class TestVerification(unittest.TestCase):
	def test_glb_tronque(self):
		with tempfile.TemporaryDirectory() as d:
			g = modeles.Gltf()
			c = visuels.Calque(64, 64, (200, 0, 0))
			g.noeud("Booster", g.mesh("m", g.geometrie(modeles.maillage_booster()), g.materiau("m", c)))
			bon = os.path.join(d, "bon.glb")
			g.ecrire(bon)
			self.assertEqual(verification.verifier_glb(bon), ([], 1))
			mauvais = os.path.join(d, "mauvais.glb")
			open(mauvais, "wb").write(open(bon, "rb").read()[:-200])
			self.assertTrue(verification.verifier_glb(mauvais)[0])

	def test_fiche_invalide(self):
		erreurs = series.verifier_fiche("x", {"style": "baroque", "fond": "zz", "heros": [], "figurants": []})
		self.assertTrue(any("style" in e for e in erreurs))
		self.assertTrue(any("fond" in e for e in erreurs))
		self.assertTrue(any("héros" in e for e in erreurs))


class TestMiseEnPage(unittest.TestCase):
	def test_monstre_jamais_sous_le_texte(self):
		serie = {"style": "mecha", "logo": ("TEST", "SERIES"), "police": "ronde", "fond": "102030",
			"accent": "ff8800", "accent2": "66ddff", "encre": "050505", "interieur": "203040"}
		c = visuels.Calque(400, 600, (20, 20, 40))
		bete = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
		ImageDraw.Draw(bete).ellipse((10, 10, 290, 290), fill=(200, 80, 80, 255))
		visuels.RAPPORT.clear()
		p = visuels.Plan(c, serie, "test")
		p.logo(200, 100, 360, 120)
		p.bandeau(200, 520, 300, 50, "BOOSTER PACK")
		p.monstre(bete, (10, 10, 390, 590), 200, 380, 500, nom="rond")
		p.dessiner()
		(_, nom, echelle, cache), = visuels.RAPPORT
		self.assertEqual(cache, 0.0)
		self.assertGreater(echelle, 0.3)


if __name__ == "__main__":
	unittest.main()
