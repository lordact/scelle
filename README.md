# Scellé — boosters et displays en 3D pour Card Hustle

Fabrique automatiquement, pour chaque série du jeu, les modèles 3D Godot
(`.glb`, textures embarquées) de son produit scellé :

| Modèle | Fichiers (par série) |
|---|---|
| 4 boosters, chacun avec son monstre vedette | `booster_<1-4>_<édition>.glb` |
| demi-display de 12 boosters, fermé et ouvert | `demi_display_<ferme\|ouvert>_<édition>.glb` |
| display de 24 boosters, fermé et ouvert | `display_<ferme\|ouvert>_<édition>.glb` |

`<édition>` : `unlimited` (Reprint) ou `first_edition` (pastille « 1st Edition »),
les clés de `addons/card_shop/sealed.json`. Soit 16 modèles par série.

## Ajouter une série

La série doit d'abord exister dans le jeu : ses cartes dans CardForge
(`CardForge/series/<id>/serie.json` et ses illustrations) et son produit dans
la boutique (`addons/card_shop/sealed.json` : nom, code). Puis, dans le jeu :

```sh
python3 Contenu/Scelle/Outils/scelle.py
```

Sans commande, l'outil trouve chaque série de `sealed.json` qui n'a pas encore
de scellé et fait tout :

1. trouve une illustration par créature dans CardForge (l'Ultra de préférence) ;
2. choisit le style d'après les illustrations : dessin animé (aplats) → `cosmic`,
   peu saturé (métal, béton) → `mecha`, peinture riche → `mythic` ;
3. détoure tous les monstres (rembg), avec le modèle qui convient au style, et
   note chaque détourage ;
4. retient les 4 héros (un par booster) et 5 figurants (displays) sur la qualité
   du détourage et la variété des couleurs ;
5. tire la palette des illustrations et le logo du nom de la série ;
6. écrit la fiche `Contenu/Scelle/Series/<id>.json` ;
7. génère les 16 modèles, met à jour `Contenu/Scelle/Apercu.tscn` et vérifie tout.

La fiche reste modifiable à la main (changer un héros, une couleur, le style),
puis `scelle.py generer <id>` refait les modèles.

## Commandes

```sh
python3 Contenu/Scelle/Outils/scelle.py                     # ce qui manque, puis vérification
python3 Contenu/Scelle/Outils/scelle.py ajouter <id>         # une série précise (--style, --remplacer)
python3 Contenu/Scelle/Outils/scelle.py generer [ids]        # refaire les modèles
python3 Contenu/Scelle/Outils/scelle.py detourer [ids]       # refaire les détourages des fiches
python3 Contenu/Scelle/Outils/scelle.py verifier             # fiches, détourages, 16 .glb valides
python3 Contenu/Scelle/Outils/scelle.py planches --godot <godot> [ids]   # rendus Godot en planches
```

Options : `--jeu <dossier>` (par défaut le projet qui contient l'outil),
`--moteur simple` (détourage sans rembg, pour des fonds unis).

## Ce que garantit la génération

- Chaque monstre est posé en entier, jamais sous un texte (logo, cartouche,
  encart, pastille d'édition) ni sous la jupe du couvercle ; la génération
  s'arrête en erreur sinon.
- Aucun monstre ne se répète sur les faces d'une boîte vues ensemble.
- Chaque `.glb` est relu : en-tête, accesseurs, images, nombre de boosters
  (1, 12 ou 24).

## Dépendances

- Génération : Python 3, numpy, Pillow.
- Détourage d'une nouvelle série : `pip install rembg onnxruntime scipy` (les
  modèles u2net et isnet se téléchargent au premier lancement).
- Planches : Godot 4.4 (et `xvfb-run` sans écran).

## Dans ce dépôt

| Dossier | Dans le jeu |
|---|---|
| `scelle/` : l'outil (`scelle.py`), les visuels (`visuels.py`), les modèles 3D (`modeles.py`), les fiches (`series.py`), le détourage (`detourage.py`), la vérification des `.glb` | `Contenu/Scelle/Outils/` |
| `tests/` | `Contenu/Scelle/Outils/tests/` |

Les fiches, détourages et modèles appartiennent au jeu (`Contenu/Scelle/`),
pas à ce dépôt. Intégration dans le jeu :

```sh
python3 Outils/integration/integrer_module.py scelle ../scelle               # simulation
python3 Outils/integration/integrer_module.py scelle ../scelle --appliquer
```

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Ils montent un faux jeu (une série inventée de 7 créatures dessinées) et la
font passer par toute la chaîne avec le détourage simple : pas besoin de rembg
ni des illustrations du jeu.
