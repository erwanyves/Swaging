# -*- coding: utf-8 -*-
"""Swaging — construction du sertissage : VarSet, esquisse et révolution.

Le profil (21 géométries, 52 contraintes, 8 expressions) est décrit dans
`data/swaging.json`, extrait du modèle de référence. Ce module ne
contient aucune coordonnée en dur : il lit les données, les translate
radialement pour les amener sur l'arête choisie, puis reconstruit l'esquisse.

Ordre de construction retenu, et la raison :

1. le VarSet est créé avec les **valeurs du modèle de référence**, seul
   `InnerRadius` étant porté au rayon de l'arête ;
2. l'esquisse est construite avec ces mêmes valeurs, sur une géométrie déjà
   translatée du même écart — elle démarre donc exactement à sa solution, le
   solveur n'a rien à déplacer ;
3. les expressions relient les contraintes au VarSet (sans rien changer,
   puisque les valeurs coïncident) ;
4. la révolution est ajoutée, le document est recalculé ;
5. **seulement ensuite** les valeurs choisies par l'utilisateur sont écrites
   dans le VarSet et le document recalculé une seconde fois.

Faire l'inverse (construire directement aux valeurs utilisateur) obligerait le
solveur à partir d'un état incohérent, avec le risque classique de basculer
sur une solution miroir.
"""

import io
import json
import math
import os

import FreeCAD as App
import Part
import Sketcher

from . import aspect
from . import i18n

_NOM_SKETCH = 'SwagingSketch'
_NOM_REVOLUTION = 'Swaging'
_NOM_VARSET = 'SwagingVarSet'

# Marqueur d'identification d'un sertissage.
#
# Il est posé sur la RÉVOLUTION, et non sur le Body ni sur le seul VarSet :
# un Body peut porter plusieurs sertissages (décision de l'utilisateur du
# 15/09/2026), et le VarSet est un satellite de l'opération, pas l'opération.
# C'est `SWG_Version` qui sert de propriété identifiante à SmartFinder, sur
# le modèle de `oring_version` (ORing) et `SC_Standard`
# (StandardPartSelector).
#
# `SWG_VarSet` porte le lien opération -> paramètres. Il rend la résolution
# indépendante de l'endroit où le VarSet est finalement rangé : si une
# version de FreeCAD refusait de le garder dans le Body, rien ne casse.
#
# Une SECONDE propriété, `SWG_Corps`, est posée sur le Body. Elle ne dit pas
# la même chose : « ce corps contient au moins un sertissage », et rien de
# plus. Elle existe parce que SmartFinder pose exactement cette question-là
# et ne sait y répondre que sur un objet atteignable en REMONTANT depuis la
# sélection (`detector.py::resolve_selected_component`, qui ne descend
# jamais dans le `Group`). Or la sélection rend le Tip du corps : dès qu'une
# opération suit le sertissage, `SWG_Version` lui est invisible.
# L'identité, elle, reste sur l'opération (décision du 15/09/2026).
SWAGING_VERSION = '1.0'
_PROP_VERSION = 'SWG_Version'
_PROP_VARSET = 'SWG_VarSet'
_PROP_CORPS = 'SWG_Corps'
_GROUPE_MARQUEUR = 'Swaging'

# Paramètres dont `verifier_valeurs()` connaît la sémantique. Regroupés ici
# pour que le reste du module reste piloté par les données du JSON.
_P_RAYON = 'InnerRadius'
_P_RAYON_SERT = 'SwagingRadius'
_P_ANGLE = 'SwagingAngle'
_P_LEVRE = 'LipLength'
_P_ANGLE_NON_SERTI = 'UnswagedAngle'


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------

def chemin_donnees():
    """Chemin du fichier de description du profil."""
    ici = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(ici), 'data', 'swaging.json')


def charger():
    """Description du profil, telle que lue sur disque."""
    with io.open(chemin_donnees(), 'r', encoding='utf-8') as fichier:
        return json.load(fichier)


def parametres(data):
    """Liste ordonnée des descripteurs de paramètres du VarSet."""
    return list(data['varset']['parametres'])


def valeurs_reference(data):
    """Valeurs du modèle de référence, par nom de paramètre."""
    return dict((p['nom'], float(p['defaut'])) for p in parametres(data))


def nom_parametre_rayon(data):
    """Nom du paramètre initialisé depuis l'arête sélectionnée."""
    return data['sketch']['contrainte_rayon']


def nom_varset():
    """Nom de base des VarSets créés par Swaging.

    Exposé pour que `geometrie.inventaire_parametres()` puisse reconnaître
    le VarSet d'un autre sertissage sans importer ce module — l'inverse
    créerait un cycle d'imports.
    """
    return _NOM_VARSET


# ---------------------------------------------------------------------------
# État serti / non serti
# ---------------------------------------------------------------------------
#
# Une même pièce a deux représentations : sertie (lèvre rabattue à l'angle
# nominal) et non sertie (lèvre droite, telle qu'elle sort d'usinage). La
# longueur DÉVELOPPÉE est conservée de l'une à l'autre — c'est bien la même
# matière — parce que `StraightLipLength` est le complément de l'arc.
#
# L'état vit dans le VarSet, et l'esquisse le lit par une expression
# conditionnelle : l'angle nominal reste donc intact pendant que la pièce est
# représentée non sertie, et l'état peut lui-même être piloté depuis un
# assemblage.
#
# ⚠ Mesuré le 24/09/2026 (`SONDE_representation_sertie_swaging`) : à 0°
# exactement, le solveur NE PROTESTE PAS — l'esquisse reste entièrement
# contrainte, la forme reste valide, et le volume tombe de 12 665 à
# 6 888 mm³. Zéro ne se refuse donc pas tout seul : d'où l'angle de repli, et
# le garde-fou de `verifier_valeurs()`.


def parametres_etat(data):
    """Descripteurs des propriétés d'état à poser sur le VarSet.

    Une liste, et non un descripteur seul : elle se parcourt comme
    `parametres()`, à la création comme à la mise à niveau.
    """
    descripteur = data.get('etat', {}).get('parametre')
    return [descripteur] if descripteur else []


def nom_parametre_etat(data):
    """Nom de la propriété booléenne portant l'état serti / non serti."""
    return data.get('etat', {}).get('parametre', {}).get('nom', '')


def nom_parametre_angle_non_serti(data):
    """Nom du paramètre donnant l'angle de la représentation non sertie."""
    return data.get('etat', {}).get('angle', '')


def etat_disponible(varset, data):
    """Vrai si le VarSet porte la propriété d'état.

    Un sertissage créé avant le 24/09/2026 ne la porte pas : la boîte doit
    le SAVOIR pour griser le choix, plutôt qu'afficher un bouton sans effet.
    """
    nom = nom_parametre_etat(data)
    return bool(nom) and hasattr(varset, nom)


def etat_serti(varset, data):
    """Vrai si le sertissage est représenté serti.

    Un VarSet qui ne porte pas la propriété rend **True** : c'est la forme
    historique, et toute autre réponse changerait l'aspect d'une pièce
    existante à la simple ouverture de la boîte.
    """
    nom = nom_parametre_etat(data)
    if not nom:
        return True
    try:
        return bool(getattr(varset, nom))
    except Exception:
        return True


def appliquer_etat(varset, data, serti):
    """Écrit l'état dans le VarSet. Vrai s'il a été écrit.

    ⚠ Un état PILOTÉ par une expression n'est pas écrit — même règle que
    `appliquer_valeurs()` : l'écriture serait refusée par FreeCAD ou défaite
    au recalcul suivant, et l'utilisateur croirait son choix pris en compte.
    Le saut est journalisé, jamais silencieux.
    """
    nom = nom_parametre_etat(data)
    if not nom or not hasattr(varset, nom):
        return False
    if nom in parametres_pilotes(varset):
        App.Console.PrintLog(
            '[Swaging] %s\n' % i18n.tr('msg.pilotage_ecriture_sautee',
                                       parametre=nom))
        return False
    setattr(varset, nom, bool(serti))
    return True


def angle_effectif(valeurs, serti=True):
    """Angle que l'esquisse reçoit réellement, selon l'état.

    Le champ « angle de sertissage » garde sa valeur en mode non serti : il
    porte l'angle qui reprendra la main au retour (décision du 24/09/2026).
    """
    if serti:
        return float(valeurs.get(_P_ANGLE, 0.0))
    return float(valeurs.get(_P_ANGLE_NON_SERTI, 0.0))


def mettre_a_niveau_etat(varset, sketch, data):
    """Complète un sertissage antérieur à l'état serti / non serti.

    Rend un rapport — `{'proprietes': [...], 'expressions': {chemin:
    ancienne}, 'refus': [(chemin, expression)]}` — qui sert à deux choses :
    DIRE à l'utilisateur ce qui a été fait, et permettre de le DÉFAIRE.

    Deux listes blanches, jamais une liste noire :

    - seuls les chemins nommés par `migration.expressions_anterieures` sont
      regardés ; aucune autre expression de l'esquisse n'est touchée ;
    - et parmi eux, seule une expression RECONNUE (absente, ou identique à
      une forme antérieure connue) est réécrite. Une expression que
      l'utilisateur a retouchée est laissée en place et NOMMÉE dans le
      rapport : réécrire ce qu'on ne reconnaît pas, c'est détruire.
    """
    rapport = {'proprietes': [], 'expressions': {}, 'refus': []}
    groupe = data['varset'].get('groupe', 'Base')
    for descripteur in parametres_etat(data):
        nom = descripteur['nom']
        if hasattr(varset, nom):
            continue
        varset.addProperty(descripteur['type'], nom, groupe,
                           i18n.tr(descripteur['doc_cle']))
        setattr(varset, nom, bool(descripteur['defaut']))
        rapport['proprietes'].append(nom)
    nom_angle = nom_parametre_angle_non_serti(data)
    for descripteur in parametres(data):
        if descripteur['nom'] != nom_angle or hasattr(varset, nom_angle):
            continue
        varset.addProperty(descripteur['type'], nom_angle, groupe,
                           i18n.tr(descripteur['doc_cle']))
        setattr(varset, nom_angle, float(descripteur['defaut']))
        rapport['proprietes'].append(nom_angle)
    table = data.get('migration', {}).get('expressions_anterieures', {})
    portees = expressions_pilotes(sketch)
    for entree in data['sketch']['expressions']:
        if entree['chemin'] not in table:
            continue
        chemin = entree['chemin'].lstrip('.')
        attendue = entree['expression'].replace('{VARSET}', varset.Name)
        actuelle = portees.get(chemin)
        if actuelle == attendue:
            continue
        anciennes = [g.replace('{VARSET}', varset.Name)
                     for g in table[entree['chemin']]]
        if actuelle is not None and actuelle not in anciennes:
            rapport['refus'].append((chemin, actuelle))
            continue
        sketch.setExpression(chemin, attendue)
        rapport['expressions'][chemin] = actuelle
    return rapport


def defaire_mise_a_niveau(varset, sketch, rapport):
    """Défait ce que `mettre_a_niveau_etat()` a posé. Ne lève jamais.

    L'abandon de transaction suffit normalement — mesuré le 24/09/2026, il
    défait jusqu'à `addProperty`. Ce filet reste parce qu'un état relu vaut
    mieux qu'un état supposé, et il est idempotent : ce qui a déjà disparu
    est simplement ignoré.
    """
    if not rapport:
        return
    for chemin, ancienne in (rapport.get('expressions') or {}).items():
        try:
            sketch.setExpression(chemin, ancienne)
        except Exception as erreur:
            App.Console.PrintWarning('[Swaging] %s\n' % erreur)
    for nom in (rapport.get('proprietes') or []):
        if not hasattr(varset, nom):
            continue
        try:
            varset.removeProperty(nom)
        except Exception as erreur:
            App.Console.PrintWarning('[Swaging] %s\n' % erreur)


# ---------------------------------------------------------------------------
# Pilotage du rayon par un paramètre nommé du document
# ---------------------------------------------------------------------------
#
# Demande de l'utilisateur du 21/09/2026, spécifiée dans
# `claude/spec_swaging_rayon_pilote_par_parametre.md`.
#
# Le rayon de l'arête est la SEULE valeur gravée de toute la chaîne : la
# contrainte `InnerRadius` suit déjà `{VARSET}.InnerRadius` par expression,
# et l'esquisse comme la révolution suivent la contrainte. Lier le rayon à
# un paramètre du document revient donc à poser une expression sur cette
# propriété-là, et rien d'autre ne bouge.
#
# `candidats_pilotage()` est PURE : elle reçoit l'inventaire déjà extrait du
# document par `geometrie.inventaire_parametres()`. C'est ce qui permet de
# l'éprouver hors FreeCAD (mémorandum §2.2 point 11).

TOLERANCE_PILOTAGE = 1e-6

ROLE_RAYON = 'RAYON'
ROLE_DIAMETRE = 'DIAMETRE'


def _expression_pour(chemin, role):
    """Expression qui amène ce paramètre au RAYON attendu par le VarSet."""
    return chemin if role == ROLE_RAYON else '%s / 2' % chemin


def dans_perimetre(entree, conteneurs_admis):
    """L'entrée vit-elle dans un conteneur admis ? Fonction PURE.

    `conteneurs_admis` à None : aucun filtrage. C'est le cas quand le
    corps n'est pas connu — voir `geometrie.portee_corps()`.
    """
    if conteneurs_admis is None:
        return True
    return (entree.get('conteneur') or '') in conteneurs_admis


def candidats_pilotage(inventaire, rayon, esquisses_source=(),
                       conteneurs_admis=None,
                       tolerance=TOLERANCE_PILOTAGE):
    """Paramètres nommés susceptibles de piloter le rayon. Fonction PURE.

    `inventaire` : la liste rendue par `geometrie.inventaire_parametres()`.
    `esquisses_source` : les noms rendus par `geometrie.esquisses_source()`.

    Le RÔLE n'est pas deviné d'après le nom du paramètre — un nom peut
    mentir — mais d'après sa VALEUR : égale au rayon, il est un rayon ;
    égale au diamètre, un diamètre, et l'expression porte le `/ 2`.

    Le CLASSEMENT tient en trois critères, dans cet ordre (décisions de
    l'utilisateur du 21/09) :

    1. **un RELAIS en tout dernier** — un paramètre déjà porté par une
       expression n'est pas une source : il en a une, et cette source-là
       fait mieux l'affaire, sans détour. *Mesuré le 21/09 sur une seconde
       arête : `SwagingSketch.Constraints.InnerRadius` remontait deuxième,
       marqué « pilote cette arête » — c'était vrai, et c'était un relais
       vers `SwagingVarSet.InnerRadius`, présent dans la même liste.* Ce
       critère passe **avant** la généalogie : un relais hérite la sienne
       de sa source, qui la porte tout aussi bien ;
    2. **la généalogie ensuite** — un paramètre qui appartient à une
       esquisse ayant produit l'arête la pilote réellement ; les autres ne
       font que porter la même valeur, ce qui peut être une coïncidence ;
    3. **les VarSets de Swaging en dernier de leur groupe** — le
       `InnerRadius` d'un autre sertissage porte par construction le rayon
       de son arête, donc deux sertissages sur le même alésage se
       correspondent toujours. Lier l'un à l'autre est légitime, mais ce
       n'est pas ce qu'on attend en tête.

    Aucun n'est jamais ÉCARTÉ par le CLASSEMENT, seulement relégué :
    c'est à l'auteur du modèle de décider.

    Le PÉRIMÈTRE, lui, écarte — et c'est le seul endroit qui le
    fasse. `conteneurs_admis` vient de `geometrie.portee_corps()` :
    un paramètre vivant dans un AUTRE corps n'est pas proposé
    (décision de l'utilisateur du 21/09/2026, après avoir vu la
    boîte offrir les cotes d'un corps voisin). À None, rien n'est
    écarté. **Ce retrait se journalise** : un filtre muet est un
    filtre qu'on ne peut pas démentir.

    Rend une liste de nouveaux dictionnaires — l'inventaire reçu n'est pas
    modifié — portant en plus `role`, `genealogique` et `expression`.
    """
    rayon = float(rayon)
    diametre = rayon * 2.0
    sources = set(esquisses_source or ())
    retenus = []
    for rang, entree in enumerate(inventaire or ()):
        if not dans_perimetre(entree, conteneurs_admis):
            continue
        valeur = entree.get('valeur')
        if valeur is None:
            continue
        if abs(float(valeur) - rayon) <= tolerance:
            role = ROLE_RAYON
        elif abs(float(valeur) - diametre) <= tolerance:
            role = ROLE_DIAMETRE
        else:
            continue
        candidat = dict(entree)
        candidat['role'] = role
        candidat['genealogique'] = bool(entree.get('esquisse')
                                        and entree['esquisse'] in sources)
        candidat['expression'] = _expression_pour(entree['chemin'], role)
        candidat['_rang'] = rang
        retenus.append(candidat)
    retenus.sort(key=lambda c: (1 if c.get('deja_pilote') else 0,
                                0 if c['genealogique'] else 1,
                                1 if c.get('swaging') else 0,
                                c['_rang']))
    for candidat in retenus:
        candidat.pop('_rang', None)
    return retenus


# Motifs de relégation — des CLÉS i18n, pas des phrases : la décision de
# ce qu'il faut dire appartient à ce module, sa formulation au catalogue.
MOTIF_GENEALOGIQUE = 'pilotage.genealogique'
MOTIF_MEME_VALEUR = 'pilotage.meme_valeur'
MOTIF_RELAIS = 'pilotage.relais'
MOTIF_AUTRE_SERTISSAGE = 'pilotage.autre_sertissage'

COTE_RAYON = 'choix.cote_rayon'
COTE_DIAMETRE = 'choix.cote_diametre'


def lignes_pilotage(candidats):
    """Ce que la boîte de choix affichera, ligne par ligne. Fonction PURE.

    Rend une liste de dictionnaires `{candidat, cle, args}` — jamais de
    texte : les clés i18n sont décidées ici, la formulation appartient au
    catalogue. C'est ce qui rend l'affichage éprouvable hors FreeCAD et
    hors Qt (mémorandum §2.2 point 11).

    **La dernière ligne est toujours « ne pas lier »**, avec un candidat
    `None`. C'est l'idiome déjà retenu pour « créer un nouveau sertissage »
    dans la boîte de choix des sertissages : le refus est une entrée de la
    liste, pas un bouton — il se choisit du même geste que le reste.

    Le MOTIF affiché suit la raison du classement, la plus informative
    d'abord : un relais dit vers quoi il relaie, car c'est POURQUOI il est
    en dernier ; un paramètre d'un autre sertissage le dit ; sinon la
    généalogie, sinon la simple égalité de valeur.

    Une liste de candidats vide rend une liste vide — **pas** une boîte
    n'offrant que « ne pas lier ». Une question sans réponse possible ne se
    pose pas.
    """
    if not candidats:
        return []
    lignes = []
    for candidat in candidats:
        if candidat.get('deja_pilote'):
            motif, motif_args = MOTIF_RELAIS, {'source': candidat['deja_pilote']}
        elif candidat.get('swaging'):
            motif, motif_args = MOTIF_AUTRE_SERTISSAGE, {}
        elif candidat.get('genealogique'):
            motif, motif_args = MOTIF_GENEALOGIQUE, {}
        else:
            motif, motif_args = MOTIF_MEME_VALEUR, {}
        lignes.append({
            'candidat': candidat,
            'cle': 'choix.pilotage_ligne',
            'args': {
                'chemin':     candidat['chemin'],
                'cote_cle':   (COTE_DIAMETRE if candidat['role'] == ROLE_DIAMETRE
                               else COTE_RAYON),
                'valeur':     float(candidat['valeur']),
                'motif_cle':  motif,
                'motif_args': motif_args,
            },
        })
    lignes.append({'candidat': None,
                   'cle': 'choix.pilotage_ne_pas_lier',
                   'args': {}})
    return lignes


def expressions_pilotes(varset):
    """Expressions portées par le VarSet, par nom de propriété.

    Le dialogue en a besoin pour AFFICHER la source ; `appliquer_valeurs`
    n'a besoin que des noms. Une seule lecture pour les deux, sans quoi
    la seconde se mettrait à diverger (mémorandum, classe F).
    """
    portees = {}
    for entree in (getattr(varset, 'ExpressionEngine', None) or ()):
        try:
            portees[str(entree[0]).lstrip('.')] = str(entree[1])
        except Exception:
            continue
    return portees


def parametres_pilotes(varset):
    """Noms des propriétés du VarSet portées par une expression."""
    return set(expressions_pilotes(varset))


def lier_rayon(varset, data, expression):
    """Pose l'expression de pilotage sur le paramètre de rayon. Vrai si posée.

    L'échec est RAPPORTÉ, jamais avalé : une liaison qui n'a pas pris doit
    se voir, sans quoi l'utilisateur croira son sertissage piloté.
    """
    nom = nom_parametre_rayon(data)
    try:
        varset.setExpression(nom, expression)
    except Exception as erreur:
        App.Console.PrintWarning(
            '[Swaging] %s\n' % i18n.tr('msg.pilotage_refuse',
                                       expression=expression, erreur=erreur))
        return False
    App.Console.PrintMessage(
        '[Swaging] %s\n' % i18n.tr('msg.pilotage_pose',
                                   parametre=nom, expression=expression))
    return True


def delier_rayon(varset, data):
    """Retire l'expression de pilotage. La valeur courante est conservée."""
    nom = nom_parametre_rayon(data)
    try:
        varset.setExpression(nom, None)
    except Exception as erreur:
        App.Console.PrintWarning('[Swaging] %s\n'
                                 % i18n.tr('msg.pilotage_refuse',
                                           expression='(retrait)',
                                           erreur=erreur))
        return False
    return True


# ---------------------------------------------------------------------------
# Contrôles préalables
# ---------------------------------------------------------------------------

def verifier_valeurs(valeurs, serti=True):
    """Contrôles de cohérence des valeurs saisies.

    Retourne une liste de clés i18n (avec leurs arguments de formatage)
    décrivant les incohérences ; liste vide si tout est cohérent.

    `serti` décide de l'angle CONTRÔLÉ. Une lèvre plus courte que l'arc du
    sertissage est impossible sertie et parfaitement normale non sertie :
    contrôler l'angle nominal dans les deux cas refuserait une pièce valide,
    sans que l'utilisateur puisse comprendre pourquoi.
    """
    problemes = []
    rayon = float(valeurs.get(_P_RAYON, 0.0))
    rayon_sert = float(valeurs.get(_P_RAYON_SERT, 0.0))
    angle = math.radians(angle_effectif(valeurs, serti))
    levre = float(valeurs.get(_P_LEVRE, 0.0))
    if rayon <= 0.0:
        problemes.append(('msg.rayon_nul', {}))
        return problemes
    # Mesuré le 24/09/2026 : à 0° exactement le solveur ne proteste pas —
    # l'esquisse reste entièrement contrainte et la forme valide — mais le
    # volume tombe de moitié. Rien ne refuse ce zéro à notre place.
    if not serti and float(valeurs.get(_P_ANGLE_NON_SERTI, 0.0)) <= 0.0:
        problemes.append(('msg.angle_non_serti_nul', {}))
        return problemes
    arc = rayon_sert * angle
    if levre < arc:
        problemes.append(('msg.longueur_levre_courte',
                          {'levre': levre, 'arc': arc}))
        return problemes
    # Rayon le plus faible atteint par la lèvre : la partie courbe rentre de
    # Rs·(1-cos θ), puis la partie droite continue tangentiellement et rentre
    # de L·sin θ. Si ce rayon devient nul ou négatif, le profil traverse l'axe
    # de révolution et la révolution est impossible.
    rentree = (rayon_sert * (1.0 - math.cos(angle))
               + (levre - arc) * math.sin(angle))
    if rayon - rentree <= 0.0:
        problemes.append(('msg.profil_traverse_axe',
                          {'rayon': rayon, 'rentree': rentree}))
    return problemes


# ---------------------------------------------------------------------------
# Géométrie
# ---------------------------------------------------------------------------

def translater_geometries(geometries, ecart):
    """Copie des géométries décalées de `ecart` selon X (direction radiale).

    Un cas particulier : une géométrie portant `ajustement = p2_sur_axe_v` a
    son extrémité contrainte sur l'axe vertical de l'esquisse. La translation
    l'en écarterait ; la direction d'origine est donc conservée et le segment
    prolongé jusqu'à x = 0.

    Ce prolongement n'est appliqué que s'il va vers l'avant (t > 0). Sur un
    rayon très petit, le point de départ passe de l'autre côté de l'axe et le
    prolongement repartirait en arrière, donnant au solveur une amorce sur la
    mauvaise branche (angle supplémentaire). Dans ce cas la simple translation
    est conservée : l'amorce reste sur la bonne branche et le solveur n'a plus
    qu'à faire glisser l'extrémité sur l'axe.
    """
    resultat = []
    for source in geometries:
        geo = dict(source)
        if geo['type'] == 'ligne':
            p1 = [geo['p1'][0] + ecart, geo['p1'][1]]
            p2 = [geo['p2'][0] + ecart, geo['p2'][1]]
            if geo.get('ajustement') == 'p2_sur_axe_v':
                dx = geo['p2'][0] - geo['p1'][0]
                dy = geo['p2'][1] - geo['p1'][1]
                if abs(dx) > 1e-12:
                    t = (0.0 - p1[0]) / dx
                    if t > 0.0:
                        p2 = [0.0, p1[1] + t * dy]
            geo['p1'], geo['p2'] = p1, p2
        elif geo['type'] in ('cercle', 'arc'):
            geo['centre'] = [geo['centre'][0] + ecart, geo['centre'][1]]
        elif geo['type'] == 'point':
            geo['p'] = [geo['p'][0] + ecart, geo['p'][1]]
        else:
            raise ValueError('type de géométrie inconnu : %s' % geo['type'])
        resultat.append(geo)
    return resultat


def _geometrie_part(geo):
    """Objet `Part` correspondant à un descripteur de géométrie."""
    normale = App.Vector(0, 0, 1)
    if geo['type'] == 'ligne':
        return Part.LineSegment(App.Vector(geo['p1'][0], geo['p1'][1], 0),
                                App.Vector(geo['p2'][0], geo['p2'][1], 0))
    if geo['type'] == 'cercle':
        return Part.Circle(App.Vector(geo['centre'][0], geo['centre'][1], 0),
                           normale, geo['rayon'])
    if geo['type'] == 'arc':
        cercle = Part.Circle(App.Vector(geo['centre'][0], geo['centre'][1], 0),
                             normale, geo['rayon'])
        return Part.ArcOfCircle(cercle, geo['debut'], geo['fin'])
    if geo['type'] == 'point':
        return Part.Point(App.Vector(geo['p'][0], geo['p'][1], 0))
    raise ValueError('type de géométrie inconnu : %s' % geo['type'])


# ---------------------------------------------------------------------------
# Création des objets
# ---------------------------------------------------------------------------

def _conteneur_de(objet):
    """Nom du conteneur géométrique réel de `objet`, ou None.

    Lu et non supposé : c'est la seule façon de savoir où FreeCAD a
    effectivement rangé un objet après une demande de rangement.
    """
    try:
        parent = objet.getParentGeoFeatureGroup()
    except Exception:
        return None
    return getattr(parent, 'Name', None)


def _ranger_dans(body, objet):
    """Range `objet` dans `body`, puis RELIT où il a réellement atterri.

    Deux voies, comme pour `_rendre_non_pilotante` : l'API de groupe
    (`addObject`), puis l'affectation directe de `Group` si la première
    refuse. Rien ne garantit qu'un `PartDesign::Body` accepte un objet qui
    n'est pas une fonction PartDesign, et un refus peut être **silencieux** —
    d'où la relecture.

    Retourne le nom du conteneur obtenu, ou None. Un échec n'est pas fatal :
    le lien `SWG_VarSet` porté par la révolution rend la résolution
    indépendante de l'emplacement du VarSet.
    """
    voies = []
    try:
        body.addObject(objet)
        voies.append('addObject')
    except Exception as erreur:
        App.Console.PrintLog('[Swaging] %s.addObject(%s) refusé : %s\n'
                             % (body.Name, objet.Name, erreur))
        try:
            groupe = list(getattr(body, 'Group', []) or [])
            if objet not in groupe:
                groupe.append(objet)
            body.Group = groupe
            voies.append('Group')
        except Exception as erreur2:
            App.Console.PrintLog('[Swaging] %s.Group refusé aussi : %s\n'
                                 % (body.Name, erreur2))
            return None
    conteneur = _conteneur_de(objet)
    App.Console.PrintLog('[Swaging] %s rangé par %s -> conteneur relu : %s '
                         '(demandé : %s)\n'
                         % (objet.Name, '+'.join(voies) or 'aucune',
                            conteneur, body.Name))
    return conteneur


def creer_varset(body, data, rayon_arete, label,
                 expression_rayon=None):
    """VarSet portant les paramètres éditables, aux valeurs de référence.

    Le VarSet est créé dans le document puis **rangé dans le Body** qui porte
    l'opération : les paramètres vivent à côté de ce qu'ils pilotent (demande
    de l'utilisateur du 15/09/2026). Le rangement est relu, jamais supposé —
    voir `_ranger_dans`.
    """
    document = body.Document
    varset = document.addObject('App::VarSet', _NOM_VARSET)
    varset.Label = label
    groupe = data['varset'].get('groupe', 'Base')
    for descripteur in parametres(data):
        varset.addProperty(descripteur['type'], descripteur['nom'], groupe,
                           i18n.tr(descripteur['doc_cle']))
        setattr(varset, descripteur['nom'], float(descripteur['defaut']))
    # Le rayon : gravé, ou PILOTÉ par un paramètre nommé du document.
    # C'était la seule valeur gravée de toute la chaîne — tout l'aval
    # (contrainte `InnerRadius`, esquisse, révolution) suit déjà cette
    # propriété par expression.
    #
    # Si la liaison échoue, on grave : une expression refusée ne doit
    # pas laisser le sertissage sans rayon.
    if not (expression_rayon
            and lier_rayon(varset, data, expression_rayon)):
        setattr(varset, nom_parametre_rayon(data), float(rayon_arete))
    _ranger_dans(body, varset)
    return varset


def _offset_attachement(inverser):
    """Rotation amenant le repère de l'arête sur le plan de l'esquisse.

    `Concentric` pose un repère centré sur l'arête, Z le long de son axe.
    Une rotation de 90° autour de X amène ce Z sur l'axe vertical de
    l'esquisse — l'axe de révolution — et laisse X sur la direction radiale.
    Inverser fait tourner de -90° : le sertissage part de l'autre côté du
    plan de l'arête, le sens radial est inchangé.
    """
    return App.Placement(
        App.Vector(0, 0, 0),
        App.Rotation(App.Vector(1, 0, 0), -90.0 if inverser else 90.0))


def regler_sens(sketch, inverser):
    """Change le sens d'insertion d'une esquisse déjà attachée.

    Utilisé par l'aperçu en direct : seul l'AttachmentOffset change, ni la
    géométrie ni les contraintes ne sont touchées.
    """
    sketch.AttachmentOffset = _offset_attachement(inverser)


def _attacher(sketch, support, nom_edge, inverser):
    """Attache l'esquisse à l'arête, plan XZ du repère qu'elle définit."""
    reference = [(support, (nom_edge,))]
    if hasattr(sketch, 'AttachmentSupport'):
        sketch.AttachmentSupport = reference
    else:  # FreeCAD < 1.0
        sketch.Support = reference
    sketch.MapMode = 'Concentric'
    sketch.AttachmentOffset = _offset_attachement(inverser)


def _ajouter_geometries(sketch, data, ecart):
    """Ajoute les géométries et vérifie que les index restent alignés."""
    for geo in translater_geometries(data['sketch']['geometries'], ecart):
        index = sketch.addGeometry(_geometrie_part(geo),
                                   bool(geo.get('construction')))
        if index != geo['i']:
            raise RuntimeError(
                'index de géométrie inattendu : %s obtenu, %s attendu'
                % (index, geo['i']))


def _valeur_contrainte(contrainte, remplacements):
    """Valeur à passer au constructeur `Sketcher.Constraint`."""
    nom = contrainte.get('nom')
    if nom is not None and nom in remplacements:
        return float(remplacements[nom])
    return float(contrainte['valeur'])


def _est_pilotante(sketch, index):
    """État pilotant réel de la contrainte, relu dans l'esquisse."""
    try:
        return bool(sketch.Constraints[index].IsDriving)
    except Exception:
        return True


def _rendre_non_pilotante(sketch, index):
    """Force la contrainte en cote de référence. Vrai si le compte y est.

    Deux voies possibles selon la version de FreeCAD — `IsDriving` posé sur
    l'objet `Sketcher.Constraint` avant ajout, ou `setDriving()` après. Aucune
    n'est supposée acquise : le résultat est **relu** dans l'esquisse. Les
    erreurs rencontrées sont journalisées et non avalées — un `except` muet
    ici est exactement ce qui a laissé passer le premier défaut trouvé en
    conditions réelles. Le canal est `PrintLog` et non `PrintWarning` : sur
    les versions de FreeCAD qui refusent `setDriving`, l'échec est attendu et
    sans effet sur la géométrie ; il reste lisible en activant les messages
    journalisés dans la vue Rapport.
    """
    if not _est_pilotante(sketch, index):
        return True
    try:
        sketch.setDriving(index, False)
    except Exception as erreur:
        App.Console.PrintLog('[Swaging] setDriving(%d, False) a échoué : '
                             '%s\n' % (index, erreur))
        return False
    return not _est_pilotante(sketch, index)


def _ajouter_contraintes(sketch, data, remplacements):
    """Ajoute les contraintes une par une, et retourne les index obtenus.

    Une par une plutôt qu'en lot : la géométrie démarre à sa solution, donc
    chaque solve intermédiaire est un no-op, et en cas d'échec l'index fautif
    est connu précisément.

    Une contrainte non pilotante qui ne peut pas être rendue telle est
    **retirée** plutôt que laissée en place : la garder pilotante ajouterait
    un degré de liberté contraint de trop et rendrait l'esquisse surcontrainte
    à chaque recalcul. C'est le défaut trouvé au premier essai réel
    (09/09/2026) — la cote de longueur d'arc, purement informative, suffisait
    à faire signaler une contrainte redondante par FreeCAD.

    Le retrait est journalisé en `PrintLog` et non en `PrintWarning` : il est
    le comportement normal sur les versions de FreeCAD concernées, et un
    avertissement à chaque création faisait croire à une anomalie (constat
    utilisateur du 15/09/2026).
    """
    index_reels = {}
    for contrainte in data['sketch']['contraintes']:
        arguments = list(contrainte['args'])
        if 'valeur' in contrainte:
            arguments.append(_valeur_contrainte(contrainte, remplacements))
        pilotante = contrainte.get('pilotante', True)
        try:
            objet = Sketcher.Constraint(contrainte['type'], *arguments)
            if not pilotante:
                try:
                    objet.IsDriving = False
                except Exception as erreur:
                    App.Console.PrintLog(
                        '[Swaging] IsDriving non posable avant ajout : %s\n'
                        % erreur)
            index = sketch.addConstraint(objet)
        except Exception as erreur:
            if not pilotante:
                App.Console.PrintLog(
                    '[Swaging] %s (%s)\n'
                    % (i18n.tr('msg.contrainte_ref_ignoree'), erreur))
                continue
            raise RuntimeError(i18n.tr('msg.echec_contrainte',
                                       index=contrainte['i'],
                                       type=contrainte['type'],
                                       erreur=erreur))
        if not pilotante and not _rendre_non_pilotante(sketch, index):
            sketch.delConstraint(index)
            App.Console.PrintLog('[Swaging] %s\n'
                                 % i18n.tr('msg.contrainte_ref_ignoree'))
            continue
        index_reels[contrainte['i']] = index
    return index_reels


def _renommer_contraintes(sketch, data, index_reels):
    """Applique les noms des contraintes pilotées par le VarSet."""
    for contrainte in data['sketch']['contraintes']:
        nom = contrainte.get('nom')
        if not nom:
            continue
        index = index_reels.get(contrainte['i'])
        if index is None:
            continue
        sketch.renameConstraint(index, nom)


def _poser_expressions(sketch, data, varset):
    """Relie les contraintes nommées au VarSet."""
    for entree in data['sketch']['expressions']:
        chemin = entree['chemin'].lstrip('.')
        expression = entree['expression'].replace('{VARSET}', varset.Name)
        sketch.setExpression(chemin, expression)


def creer_sketch(body, support, nom_edge, data, rayon_arete, inverser):
    """Esquisse du profil, attachée à l'arête, aux valeurs de référence."""
    sketch = body.newObject('Sketcher::SketchObject', _NOM_SKETCH)
    _attacher(sketch, support, nom_edge, inverser)
    ecart = float(rayon_arete) - float(data['sketch']['rayon_reference'])
    _ajouter_geometries(sketch, data, ecart)
    remplacements = {nom_parametre_rayon(data): float(rayon_arete)}
    index_reels = _ajouter_contraintes(sketch, data, remplacements)
    _renommer_contraintes(sketch, data, index_reels)
    return sketch


def creer_revolution(body, sketch, data):
    """Révolution 360° du profil autour de l'axe vertical de l'esquisse."""
    revolution = body.newObject('PartDesign::Revolution', _NOM_REVOLUTION)
    revolution.Profile = (sketch, [''])
    revolution.ReferenceAxis = (sketch, [data['revolution']['axe']])
    revolution.Angle = float(data['revolution']['angle'])
    revolution.Reversed = bool(data['revolution']['reversed'])
    revolution.Midplane = False
    sketch.Visibility = False
    return revolution


def marquer(revolution, varset):
    """Pose le marqueur d'identification sur la révolution. Vrai si posé.

    Les propriétés sont ajoutées si elles manquent, puis écrites, puis
    **relues** : `addProperty` peut échouer sur un nom déjà pris par un autre
    atelier, et l'échec serait invisible.
    """
    for nom, type_fc, cle in ((_PROP_VERSION, 'App::PropertyString',
                               'prop.swg_version'),
                              (_PROP_VARSET, 'App::PropertyLink',
                               'prop.swg_varset')):
        if hasattr(revolution, nom):
            continue
        try:
            revolution.addProperty(type_fc, nom, _GROUPE_MARQUEUR,
                                   i18n.tr(cle))
        except Exception as erreur:
            App.Console.PrintError('[Swaging] propriété %s non ajoutée sur '
                                   '%s : %s\n'
                                   % (nom, revolution.Name, erreur))
            return False
    try:
        setattr(revolution, _PROP_VERSION, SWAGING_VERSION)
        setattr(revolution, _PROP_VARSET, varset)
    except Exception as erreur:
        App.Console.PrintError('[Swaging] marqueur non écrit sur %s : %s\n'
                               % (revolution.Name, erreur))
        return False
    return getattr(revolution, _PROP_VERSION, '') == SWAGING_VERSION


def marquer_corps(body):
    """Signale que ce corps porte au moins un sertissage. Vrai si posé.

    Marqueur de FAMILLE, à l'usage de SmartFinder — jamais d'identité : il
    ne dit pas *quel* sertissage, ni combien. C'est `SWG_Version` sur
    l'opération qui identifie, et l'historique d'élément qui désigne.

    Limite assumée : si tous les sertissages d'un corps sont supprimés, la
    propriété reste. SmartFinder proposera alors Swaging à tort, et la macro
    retombera proprement sur la création — faux positif visible, jamais un
    résultat faux.
    """
    if body is None:
        return False
    if not hasattr(body, _PROP_CORPS):
        try:
            body.addProperty('App::PropertyString', _PROP_CORPS,
                             _GROUPE_MARQUEUR, i18n.tr('prop.swg_corps'))
        except Exception as erreur:
            App.Console.PrintError('[Swaging] propriété %s non ajoutée sur '
                                   '%s : %s\n'
                                   % (_PROP_CORPS, body.Name, erreur))
            return False
    try:
        setattr(body, _PROP_CORPS, SWAGING_VERSION)
    except Exception as erreur:
        App.Console.PrintError('[Swaging] marqueur de corps non écrit sur '
                               '%s : %s\n' % (body.Name, erreur))
        return False
    return getattr(body, _PROP_CORPS, '') == SWAGING_VERSION


def est_sertissage(objet):
    """Vrai si `objet` est une opération de sertissage créée par la macro.

    Le critère est la présence d'une valeur dans `SWG_Version`, jamais le
    nom de l'objet : un utilisateur renomme, et un homonyme existe toujours.
    """
    return bool(getattr(objet, _PROP_VERSION, ''))


def sertissages_du_corps(body):
    """Opérations de sertissage **contenues** dans `body`.

    Le balayage porte sur `Group`, l'arbre de CONTENANCE, et jamais sur
    `OutList` / `OutListRecursive`, qui est le graphe des dépendances et
    répondrait « oui » pour toute la pièce, en silence (défaut du
    13/09/2026).
    """
    return [objet for objet in (getattr(body, 'Group', None) or [])
            if est_sertissage(objet)]


def varset_du_sertissage(revolution):
    """VarSet piloté par cette opération, ou None si le lien est absent."""
    return getattr(revolution, _PROP_VARSET, None)


def esquisse_du_sertissage(revolution):
    """Esquisse de profil de cette opération, ou None.

    `Profile` d'une `PartDesign::Revolution` est un couple `(objet, [sous])`
    sur certaines versions et l'objet seul sur d'autres : les deux formes
    sont acceptées plutôt que l'une supposée.
    """
    profil_ = getattr(revolution, 'Profile', None)
    if isinstance(profil_, (tuple, list)):
        return profil_[0] if profil_ else None
    return profil_


# ---------------------------------------------------------------------------
# Décider : modifier un sertissage existant, ou en créer un nouveau
#
# La difficulté est propre à Swaging. Dans les autres macros, une arête
# sélectionnée ne peut désigner qu'un composant existant ; ici, une arête est
# aussi l'entrée normale d'une création. Il faut donc distinguer une arête
# **du** sertissage d'une arête **pour** un sertissage.
#
# Mesuré le 15/09/2026, et c'est ce qui commande la forme retenue :
#   - la sélection rend le **Tip** du corps, jamais la feature qui a créé la
#     face cliquée. Un test `objet is revolution` ne peut donc pas répondre
#     oui dès qu'une opération suit le sertissage ;
#   - `objet.getElementHistory(element)` rend la chaîne des features
#     d'origine, et **les objets eux-mêmes**. C'est elle qui tranche.
# ---------------------------------------------------------------------------

ACTION_MODIFIER = 'MODIFIER'    # un seul sertissage désigné : on l'ouvre
ACTION_CHOISIR = 'CHOISIR'      # plusieurs désignés : liste de choix
ACTION_CREER = 'CREER'          # l'élément ne vient d'aucun sertissage
ACTION_DEMANDER = 'DEMANDER'    # pas d'historique : poser la question
ACTION_AMBIGU = 'AMBIGU'        # arête circulaire d'un sertissage : les deux
                                # lectures sont légitimes, on demande


def sertissages_dans_histoire(histoire, body=None):
    """Opérations de sertissage citées par l'historique d'un élément.

    `histoire` est ce que rend `objet.getElementHistory(element)` : une suite
    de triplets `(objet, nom_element, ancetres)`.

    **La position dans la chaîne n'est jamais un critère.** Elle contient
    aussi l'habillage posé par-dessus (congé, chanfrein) et l'esquisse
    d'origine : « prendre le deuxième » serait juste sur le cas mesuré et
    faux partout ailleurs. Seul le marqueur décide.

    Si `body` est fourni, les opérations qui ne lui appartiennent pas sont
    écartées — une opération vivant dans un autre corps ne se modifie pas
    depuis ce clic. Le filtre porte sur la CONTENANCE (`Group`), jamais sur
    les dépendances.
    """
    contenu = None if body is None else sertissages_du_corps(body)
    retenues = []
    for entree in (histoire or []):
        if isinstance(entree, (tuple, list)):
            objet = entree[0] if entree else None
        else:
            objet = entree
        if not est_sertissage(objet):
            continue
        if contenu is not None and objet not in contenu:
            continue
        if objet not in retenues:
            retenues.append(objet)
    return retenues


def _ancetres(entree):
    """Ancêtres déclarés par une entrée d'historique. Liste, jamais None."""
    if isinstance(entree, (tuple, list)) and len(entree) > 2:
        try:
            return list(entree[2] or [])
        except Exception:
            return []
    return []


def sertissages_constructeurs(histoire, body=None):
    """Sertissages qui **créent** l'élément, et non ceux qui le portent.

    Un élément traverse toutes les opérations postérieures à celle qui l'a
    produit : l'historique les cite donc toutes, et `sertissages_dans_histoire`
    les rend toutes. Ce n'est pas faux — elles sont bien dans la chaîne —
    mais une seule l'a fabriqué.

    Le critère est **mesuré**, pas supposé (15/09/2026, corps à deux
    sertissages, chaîne d'une face du premier) :

        Swaging001   0 ancêtre    l'élément ne fait qu'y transiter
        Swaging      2 ancêtres   la face de base ET l'arête d'esquisse
                                  s'y combinent : la face naît là

    **Deux ancêtres ou plus** = une combinaison, donc une construction. Zéro
    ou un = un report. La position dans la chaîne n'entre toujours pas en
    ligne de compte : prendre « le plus profond » serait juste ici et faux
    dès qu'un sertissage en recouvre un autre.

    Rend une liste éventuellement vide — auquel cas l'appelant retombe sur la
    liste complète plutôt que de conclure qu'il n'y a rien.
    """
    retenus = sertissages_dans_histoire(histoire, body)
    if not retenus:
        return []
    constructeurs = []
    for entree in (histoire or []):
        if len(_ancetres(entree)) < 2:
            continue
        objet = entree[0] if isinstance(entree, (tuple, list)) and entree \
            else entree
        if objet in retenus and objet not in constructeurs:
            constructeurs.append(objet)
    return constructeurs


def resolution_selection(histoire, body, arete_possible=False):
    """Décide ce que la sélection demande. Rend `(action, sertissages)`.

    `arete_possible` dit si l'élément cliqué peut servir d'appui à une
    **création** — c'est-à-dire s'il s'agit d'une arête circulaire. C'est le
    paramètre qui manquait à la première version, et il change tout : un
    sertissage **produit** des arêtes circulaires, et poser un second
    sertissage sur l'une d'elles est un geste légitime (signalé par
    l'utilisateur le 15/09/2026). Rien dans l'historique ne départage les
    deux lectures, donc la macro ne tranche pas : elle demande.

    Une **face**, elle, n'est jamais une entrée de création : il n'y a rien à
    départager, la modification s'ouvre directement.

    Les sertissages « retenus » sont ceux qui ont **construit** l'élément,
    et non ceux qui se contentent de le porter (`sertissages_constructeurs`).
    C'est ce qui évite de poser une question à l'utilisateur quand une seule
    opération a réellement fabriqué la face cliquée.

    | Historique | Élément cliqué | Sertissages retenus | Action |
    |---|---|---|---|
    | disponible | face | un | `MODIFIER` |
    | disponible | face | plusieurs | `CHOISIR` |
    | disponible | arête circulaire | un ou plusieurs | `AMBIGU` |
    | disponible | quelconque | aucun | `CREER` |
    | absent ou vide | quelconque | le corps n'en porte aucun | `CREER` |
    | absent ou vide | quelconque | le corps en porte | `DEMANDER` |

    Un historique **absent** (`None` ou vide) veut dire que le document n'a
    pas de nommage topologique : la contenance ne peut plus trancher, et la
    deviner serait une faute. La macro pose alors la question plutôt que de
    choisir à la place de l'utilisateur.
    """
    if histoire:
        trouves = sertissages_dans_histoire(histoire, body)
        if not trouves:
            return (ACTION_CREER, [])
        # Parmi les sertissages cités, ceux qui ont réellement CRÉÉ
        # l'élément. Les autres se contentent de le porter et n'ont rien à
        # faire dans une question posée à l'utilisateur.
        #
        # Le repli sur la liste complète est délibéré : si aucune entrée ne
        # déclare d'ancêtres — autre version de FreeCAD, autre forme de
        # chaîne — le critère ne dit rien, et ne rien dire ne veut pas dire
        # « aucun sertissage ».
        constructeurs = sertissages_constructeurs(histoire, body)
        retenus = constructeurs if constructeurs else trouves
        if arete_possible:
            return (ACTION_AMBIGU, retenus)
        if len(retenus) == 1:
            return (ACTION_MODIFIER, retenus)
        return (ACTION_CHOISIR, retenus)
    candidats = sertissages_du_corps(body) if body is not None else []
    if not candidats:
        return (ACTION_CREER, [])
    return (ACTION_DEMANDER, candidats)


def valeurs_courantes(varset, data):
    """Valeurs actuellement portées par le VarSet, par nom de paramètre.

    Un paramètre absent du VarSet retombe sur la valeur du modèle de
    référence : un VarSet créé par une version antérieure peut ne pas porter
    un paramètre ajouté depuis.
    """
    valeurs = {}
    for descripteur in parametres(data):
        nom = descripteur['nom']
        try:
            valeurs[nom] = float(getattr(varset, nom))
        except (AttributeError, TypeError, ValueError):
            valeurs[nom] = float(descripteur['defaut'])
    return valeurs


def sens_inverse(sketch):
    """Vrai si l'esquisse est posée dans le sens inversé.

    Lu sur l'`AttachmentOffset` réel plutôt que mémorisé : c'est la seule
    source qui reste juste si l'utilisateur a retourné l'esquisse à la main.
    La comparaison se fait en appliquant les deux rotations candidates à un
    vecteur sonde et en gardant la plus proche — comparer deux rotations
    membre à membre dépendrait de la convention de représentation.
    """
    try:
        rotation = sketch.AttachmentOffset.Rotation
    except Exception:
        return False
    sonde = App.Vector(0.0, 1.0, 0.0)
    try:
        actuel = rotation.multVec(sonde)
        droit = _offset_attachement(False).Rotation.multVec(sonde)
        inverse = _offset_attachement(True).Rotation.multVec(sonde)
    except Exception:
        return False
    return (actuel - inverse).Length < (actuel - droit).Length


def appliquer_valeurs(varset, valeurs):
    """Écrit les valeurs choisies par l'utilisateur dans le VarSet.

    ⚠ **Un paramètre PILOTÉ par une expression n'est pas écrit.**
    Depuis le 21/09/2026 le rayon peut suivre un paramètre nommé du
    document ; écrire par-dessus serait au mieux refusé par FreeCAD,
    au pire défait au recalcul suivant — et dans les deux cas
    l'utilisateur croirait sa valeur prise en compte.

    Le saut est journalisé, jamais silencieux (mémorandum, classe E).
    """
    pilotes = parametres_pilotes(varset)
    for nom, valeur in valeurs.items():
        if not hasattr(varset, nom):
            continue
        if nom in pilotes:
            App.Console.PrintLog(
                '[Swaging] %s\n' % i18n.tr('msg.pilotage_ecriture_sautee',
                                          parametre=nom))
            continue
        setattr(varset, nom, float(valeur))


def diagnostic_solveur(sketch):
    """Index des contraintes signalées redondantes, en conflit ou partielles.

    Les propriétés correspondantes n'existent pas sur toutes les versions de
    FreeCAD : une absence donne une liste vide, jamais une erreur.
    """
    index = []
    for attribut in ('RedundantConstraints', 'ConflictingConstraints',
                     'PartiallyRedundant'):
        try:
            index.extend(list(getattr(sketch, attribut, ()) or ()))
        except Exception:
            continue
    return sorted(set(index))


def est_entierement_contrainte(sketch):
    """Vrai si l'esquisse est entièrement contrainte, None si indéterminable.

    Un profil reconstruit fidèlement doit l'être ; un `False` signale que la
    reconstruction a perdu une contrainte en chemin et mérite un contrôle.
    """
    try:
        return bool(sketch.FullyConstrained)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def construire(body, support, nom_edge, rayon_arete, valeurs, inverser,
               label_varset, data=None, expression_rayon=None):
    """Crée le sertissage complet dans `body`.

    Retourne `(varset, sketch, revolution, aspect_corps)` — l'apparence
    relevée est rendue à l'appelant pour qu'il puisse la reposer une dernière
    fois avant de valider : entre la création et la validation, des dizaines
    de recalculs ont eu lieu pour l'aperçu.

    **Le contrôle de transaction appartient à l'appelant.** L'aperçu en direct
    impose que les objets existent pendant toute la durée du dialogue : la
    transaction est donc ouverte avant l'appel et validée — ou abandonnée, ce
    qui défait la création — après. Regrouper le tout dans une seule
    transaction donne aussi une seule entrée d'annulation à l'utilisateur.
    """
    if data is None:
        data = charger()
    document = body.Document
    varset = creer_varset(body, data, rayon_arete, label_varset,
                          expression_rayon=expression_rayon)
    sketch = creer_sketch(body, support, nom_edge, data, rayon_arete, inverser)
    _poser_expressions(sketch, data, varset)
    # L'apparence du Tip actuel est relevée AVANT que la révolution ne prenne
    # sa place : une fonction PartDesign neuve reçoit l'apparence par défaut,
    # et comme elle devient le Tip, un corps coloré repasserait en gris.
    # (Ajouter l'esquisse ne change pas le Tip, la lecture est donc bien celle
    # de la dernière fonction solide.)
    aspect_corps = aspect.capturer(body.Tip)
    revolution = creer_revolution(body, sketch, data)
    # Les marqueurs sont posés AVANT le premier recalcul : l'un identifie
    # l'opération pour la macro, l'autre signale le corps à SmartFinder.
    marquer(revolution, varset)
    marquer_corps(body)
    aspect.appliquer(revolution, aspect_corps)
    document.recompute()
    appliquer_valeurs(varset, valeurs)
    document.recompute()
    return varset, sketch, revolution, aspect_corps
