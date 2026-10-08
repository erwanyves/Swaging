# -*- coding: utf-8 -*-
"""Résolution de la sélection 3D : arête circulaire, corps porteur, support
d'attachement.

Aucune dépendance à l'interface : ce module ne fait que de la logique pure et
peut être exercé hors dialogue.
"""

import math

import FreeCAD as App

try:
    import FreeCADGui as Gui
except ImportError:  # FreeCAD lancé sans interface
    Gui = None

# Types d'objets « lien » d'un assemblage multi-fichiers. Une sélection faite
# dans un assemblage traverse ces objets : le corps réel vit dans son propre
# document, et c'est là que le sertissage doit être créé (c'est une fonction
# de la pièce, pas un composant de l'assemblage).
_TYPES_LIENS = ('App::Link', 'App::LinkElement', 'App::LinkGroup')

_TYPES_BODY = ('PartDesign::Body',)

# Tolérance de contrôle géométrique (mm) — même ordre de grandeur que celle
# retenue dans les autres macros du projet.
_TOLERANCE_GEOM_MM = 1e-4


# ---------------------------------------------------------------------------
# Documents chargés partiellement
# ---------------------------------------------------------------------------
#
# Quand un assemblage lie un document, FreeCAD peut ne le charger que
# PARTIELLEMENT — juste ce qu'il faut pour afficher les instances. Dans cet
# état il n'y enregistre RIEN et refuse de le recalculer, et il le dit
# lui-même dans la vue Rapport :
#
#   DocumentObject.cpp(910): Changes to partial loaded document will not be
#                            saved: sertissate_test#SwagingVarSet001.Swaged
#   Document.cpp(2642):      Please reload partial document 'sertissate test'
#                            for recomputation
#
# ⚠ Mesuré sur le poste le 26/09/2026 : TROIS symptômes, une seule cause. La
# propriété d'état ajoutée au VarSet n'était pas enregistrée — donc le choix
# serti / non serti grisé à la réouverture ; le recalcul était refusé — donc
# le 3D ne suivait pas le basculement ; et les mandataires de vue du document
# partiel étaient incomplets — donc le VarSet ne s'ouvrait plus dans l'arbre.
#
# ORing porte ce correctif depuis le 13/09/2026, SpringFull depuis le 14/09.
# Swaging n'en avait AUCUNE occurrence : le motif est transposé, repli
# compris. Détection par `Partial`, complétion par `App.openDocument()`,
# succès conclu d'une RELECTURE de l'état — et refus d'écrire en dernier
# ressort, côté dialogue. FreeCAD avertissait déjà, douze fois, et la
# modification a été perdue quand même.


def document_partiel(document):
    """Vrai si `document` est chargé partiellement — écritures NON conservées.

    `Partial` est un attribut de `App::Document`. `getattr` avec repli : une
    version de FreeCAD qui ne l'exposerait pas doit dégrader vers
    « complet », jamais bloquer la macro sur une propriété absente.
    """
    if document is None:
        return False
    try:
        return bool(getattr(document, 'Partial', False))
    except Exception:
        return False


def documents_lies(document):
    """Documents atteints par les LIENS de `document`, par nom.

    Périmètre volontairement étroit, en liste BLANCHE : les trois types de
    lien de FreeCAD, résolus par `getLinkedObject(True)`. Balayer
    `App.listDocuments()` compléterait des documents sans rapport, que
    l'utilisateur n'a pas désignés.
    """
    lies = {}
    if document is None:
        return lies
    for objet in (getattr(document, 'Objects', None) or ()):
        if getattr(objet, 'TypeId', '') not in _TYPES_LIENS:
            continue
        try:
            reel = objet.getLinkedObject(True)
        except Exception:
            continue
        autre = getattr(reel, 'Document', None)
        nom = getattr(autre, 'Name', None)
        if nom and nom != getattr(document, 'Name', None):
            lies[nom] = autre
    return lies


def _rendre_actif(document):
    """Repose le document actif relevé avant la complétion. Ne lève jamais.

    `App.openDocument()` peut changer le document actif, et tout l'aval de la
    macro est enraciné dessus. Rien n'est reposé si le document est déjà
    actif : un `setActiveDocument()` inutile fait clignoter l'onglet.
    """
    nom = getattr(document, 'Name', None)
    if not nom:
        return False
    try:
        if getattr(App.ActiveDocument, 'Name', None) == nom:
            return False
        App.setActiveDocument(nom)
    except Exception:
        return False
    return True


def completer_documents_partiels(document, supplementaires=()):
    """Charge entièrement les documents PARTIELS du périmètre.

    Rend `{'completes': [...], 'echecs': [...], 'partiels_restants': [...]}`.
    **Ne lève jamais** : un échec se déclare, et c'est à l'appelant de refuser
    d'écrire. Les messages lui appartiennent aussi — ce module ne dépend pas
    de l'interface.

    Rien de nouveau n'est ouvert : un document partiel est DÉJÀ là, simplement
    incomplet.

    ⚠ Le succès se conclut d'une RELECTURE de l'état, jamais de l'absence
    d'exception : `App.openDocument()` peut rendre la main sans avoir
    complété. C'est le défaut planté n° 1 de la contre-épreuve.
    """
    rapport = {'completes': [], 'echecs': [], 'partiels_restants': []}
    cibles = {}
    for candidat in [document] + list(supplementaires or ()):
        nom = getattr(candidat, 'Name', None)
        if nom:
            cibles[nom] = candidat
    for nom, autre in documents_lies(document).items():
        cibles.setdefault(nom, autre)
    actif_avant = getattr(App, 'ActiveDocument', None)
    for nom in sorted(cibles):
        if not document_partiel(cibles[nom]):
            continue
        chemin = getattr(cibles[nom], 'FileName', '') or ''
        if not chemin:
            rapport['echecs'].append(nom)
            rapport['partiels_restants'].append(nom)
            continue
        try:
            # `hidden=True` : compléter un document lié ne doit pas ouvrir sa
            # fenêtre sous les yeux de l'utilisateur, qui travaille dans son
            # assemblage (demande du 14/09/2026, portée sur SpringFull).
            # L'argument n'existe pas sur toutes les versions de FreeCAD :
            # repli sur la forme historique plutôt qu'un échec.
            try:
                App.openDocument(chemin, True)
            except TypeError:
                App.openDocument(chemin)
        except Exception:
            rapport['echecs'].append(nom)
        try:
            apres = App.getDocument(nom)
        except Exception:
            apres = None
        if apres is not None and not document_partiel(apres):
            rapport['completes'].append(nom)
        else:
            rapport['partiels_restants'].append(nom)
    _rendre_actif(actif_avant)
    return rapport


def relever_selection():
    """Sélection courante, EN CHAÎNES : `(document, objet, sous-éléments)`.

    En chaînes et non en objets : compléter un document remplace les
    mandataires Python, et un objet relevé avant ne désigne plus rien après
    (régression payée sur ORing le 13/09/2026).

    `getSelectionEx('', 0)` — chemin NON résolu depuis la racine : c'est le
    chemin tel que l'assemblage le voit, donc celui qu'il faudra reposer.
    """
    releve = []
    if Gui is None:
        return releve
    try:
        entrees = Gui.Selection.getSelectionEx('', 0)
    except Exception:
        return releve
    for entree in (entrees or ()):
        try:
            releve.append((str(entree.DocumentName),
                           str(entree.ObjectName),
                           tuple(entree.SubElementNames or ())))
        except Exception:
            continue
    return releve


def restituer_selection(releve):
    """Repose une sélection relevée. Vrai si quelque chose a été reposé.

    Ne repose QUE si la sélection a effectivement été perdue : la reposer
    par-dessus une sélection intacte la dédoublerait, et le dialogue verrait
    deux arêtes là où l'utilisateur en a désigné une.

    Une désignation dans l'arbre ne porte aucun sous-élément : la chaîne vide
    est alors la bonne réponse.
    """
    if not releve or Gui is None:
        return False
    try:
        if Gui.Selection.getSelectionEx('', 0):
            return False
    except Exception:
        return False
    repose = False
    for document, objet, sous_elements in releve:
        for sous in (sous_elements or ('',)):
            try:
                Gui.Selection.addSelection(document, objet, sous)
                repose = True
            except Exception:
                continue
    return repose


def resoudre_objet_reel(objet):
    """Objet réellement pointé, en traversant les chaînes de liens."""
    vu = set()
    courant = objet
    while courant is not None and courant.TypeId in _TYPES_LIENS:
        if id(courant) in vu:
            break
        vu.add(id(courant))
        try:
            suivant = courant.getLinkedObject(True)
        except Exception:
            return courant
        if suivant is None or suivant is courant:
            return courant
        courant = suivant
    return courant


def _dernier_edge(nom_sous_element):
    """Dernier jeton `EdgeN` d'un chemin de sous-élément, ou None.

    Une sélection faite dans un assemblage peut produire un chemin complet
    (`Arbre.Body.Revolution.Edge12`) ; seul le dernier jeton nomme l'arête
    dans la forme de l'objet résolu.
    """
    if not nom_sous_element:
        return None
    jeton = str(nom_sous_element).split('.')[-1]
    return jeton if jeton.startswith('Edge') else None


def est_arete_circulaire(edge):
    """Vrai si `edge` porte une courbe circulaire (cercle ou arc)."""
    return bool(edge is not None
                and hasattr(edge, 'Curve')
                and hasattr(edge.Curve, 'Radius')
                and hasattr(edge.Curve, 'Axis'))


def resoudre_arete_selectionnee():
    """Première arête circulaire de la sélection 3D courante.

    Retourne un dictionnaire décrivant l'arête, ou None si la sélection n'en
    contient aucune. Ne lève jamais.
    """
    if Gui is None:
        return None
    try:
        selection = Gui.Selection.getSelectionEx()
    except Exception:
        return None
    for sel in selection or ():
        objet = resoudre_objet_reel(sel.Object)
        if objet is None:
            continue
        noms = list(sel.SubElementNames or ())
        sous_objets = list(sel.SubObjects or ())
        for rang, nom in enumerate(noms):
            court = _dernier_edge(nom)
            if court is None:
                continue
            edge = sous_objets[rang] if rang < len(sous_objets) else None
            if edge is None:
                try:
                    edge = objet.Shape.getElement(court)
                except Exception:
                    edge = None
            if not est_arete_circulaire(edge):
                continue
            return {
                'objet': objet,
                'nom_edge': court,
                'edge': edge,
                'rayon': float(edge.Curve.Radius),
                'centre': App.Vector(edge.Curve.Center),
                'axe': App.Vector(edge.Curve.Axis),
            }
    return None


def resoudre_body_depuis_objet(objet):
    """Corps PartDesign propriétaire de `objet`, ou None."""
    if objet is None:
        return None
    if objet.TypeId in _TYPES_BODY:
        return objet
    parent = None
    try:
        parent = objet.getParentGeoFeatureGroup()
    except Exception:
        parent = None
    if parent is not None and parent.TypeId in _TYPES_BODY:
        return parent
    for amont in getattr(objet, 'InList', ()) or ():
        if amont.TypeId in _TYPES_BODY:
            groupe = getattr(amont, 'Group', ()) or ()
            if objet in groupe or amont.Tip is objet:
                return amont
    return None


def histoire_element(objet, nom_element):
    """Historique de l'élément : quelles features l'ont produit.

    Rend la liste de triplets `(objet, nom_element, ancetres)` de FreeCAD, ou
    **None** quand l'information n'est pas disponible — API absente, appel en
    échec, ou document sans nommage topologique. `None` et liste vide se
    traitent pareil en aval : ils veulent dire « je ne sais pas », jamais
    « il n'y a rien ».

    Mesuré le 15/09/2026 : c'est `objet.getElementHistory(...)` qui répond.
    `objet.Shape.getElementHistory(...)` rend `None` — ce n'est pas un repli,
    et l'appeler ne servirait qu'à se donner l'illusion d'en avoir un.
    """
    if objet is None or not nom_element:
        return None
    if not hasattr(objet, 'getElementHistory'):
        return None
    try:
        return list(objet.getElementHistory(str(nom_element)) or [])
    except Exception:
        return None


def esquisses_source(objet, nom_element):
    """Esquisses qui ont produit cet élément. Liste de noms, jamais None.

    CRITÈRE (mesuré le 21/09/2026) : **une esquisse CITÉE dans la chaîne
    d'historique est une esquisse source.** Rien de plus.

    ⚠ Ce n'est PAS le critère des « deux ancêtres » de
    `profil.sertissages_constructeurs()`. Celui-là répond à une autre
    question — *lequel, parmi plusieurs sertissages, a produit cette face ?*
    — et sur une arête de création il ne trouve rien : la première mesure a
    rendu deux maillons à zéro ancêtre alors que la chaîne nommait
    l'esquisse en clair :

        [0] Pad      g1;SKT;:H61a,E   0 ancêtre(s)
        [1] Sketch   g1;SKT           0 ancêtre(s)

    *Un critère mesuré pour une question ne vaut pas pour une autre.*

    Deux portes vers l'esquisse : le maillon EST une esquisse, ou il porte
    un `Profile` qui en est une. La seconde sert les fonctions PartDesign
    dont l'historique ne cite pas l'esquisse elle-même.
    """
    trouvees = []
    for entree in (histoire_element(objet, nom_element) or ()):
        try:
            maillon = entree[0] if isinstance(entree, (tuple, list)) else entree
        except Exception:
            continue
        candidat = None
        if getattr(maillon, 'TypeId', '') == 'Sketcher::SketchObject':
            candidat = maillon
        else:
            profil_ = getattr(maillon, 'Profile', None)
            if isinstance(profil_, (tuple, list)) and profil_:
                profil_ = profil_[0]
            if getattr(profil_, 'TypeId', '') == 'Sketcher::SketchObject':
                candidat = profil_
        nom = getattr(candidat, 'Name', None)
        if nom and nom not in trouvees:
            trouvees.append(nom)
    return trouvees


def _carte_contenance(document):
    """Nom du conteneur DIRECT de chaque objet, par l'arbre `Group`.

    `Group` est l'arbre de CONTENANCE — à ne pas confondre avec
    `OutList`, qui est celui des dépendances (mémorandum §3).
    """
    carte = {}
    if document is None:
        return carte
    for conteneur in getattr(document, 'Objects', None) or ():
        try:
            membres = list(getattr(conteneur, 'Group', None) or ())
        except Exception:
            continue
        for membre in membres:
            nom = getattr(membre, 'Name', '')
            if nom:
                carte.setdefault(nom, getattr(conteneur, 'Name', ''))
    return carte


def _conteneur_lu(objet, carte):
    """Nom du conteneur de `objet`, ou `''` s'il est à la racine.

    DEUX témoins, et non un : `getParentGeoFeatureGroup()` est la
    réponse de FreeCAD lui-même, mais un objet qui n'est pas une
    GeoFeature — un `App::VarSet`, précisément celui que range
    `profil._ranger_dans()` — peut ne rien rendre. La carte de
    contenance répond alors. Un `''` signifie « racine », jamais
    « je ne sais pas » : c'est pourquoi les deux témoins sont lus
    avant de conclure.
    """
    try:
        parent = objet.getParentGeoFeatureGroup()
    except Exception:
        parent = None
    nom = getattr(parent, 'Name', None)
    if nom:
        return nom
    return carte.get(getattr(objet, 'Name', ''), '')


def portee_corps(document, body):
    """Conteneurs ACCEPTABLES pour un paramètre destiné à `body`.

    Rend un ensemble de noms, ou **None** si le corps est inconnu —
    et `None` veut dire « ne filtre rien ». Un périmètre qu'on ne
    sait pas calculer ne doit pas devenir un périmètre vide : ce
    serait retirer toute la liste sans le dire.

    Sont admis : le corps lui-même, ses conteneurs parents (un
    `App::Part` qui range le corps), et la **racine** du document —
    décision de l'utilisateur du 21/09/2026 : un VarSet global posé
    à la racine reste une source de pilotage légitime. Sont écartés
    les objets vivant dans un AUTRE corps.
    """
    nom_body = getattr(body, 'Name', '')
    if document is None or not nom_body:
        return None
    carte = _carte_contenance(document)
    admis = set(['', nom_body])
    courant = nom_body
    while True:
        parent = carte.get(courant)
        if not parent or parent in admis:
            break
        admis.add(parent)
        courant = parent
    return admis


def inventaire_parametres(document, prefixe_varset_swaging=''):
    """Paramètres nommés du document, en dictionnaires SANS objet FreeCAD.

    C'est ce qui rend `profil.candidats_pilotage()` éprouvable hors
    FreeCAD : la lecture du document est ici, la décision est là-bas
    (mémorandum §2.2 point 11).

    Périmètre arrêté par l'utilisateur le 21/09/2026 : les `App::VarSet` et
    les contraintes d'esquisse **nommées et pilotantes**. Ni tableurs, ni
    propriétés ajoutées à la main.

    Sont écartées : les contraintes de **référence** — elles ne pilotent
    rien — et les contraintes d'**angle**, qui ne peuvent pas être un rayon.

    Chaque entrée : `{source, chemin, nom, valeur, esquisse, swaging,
    deja_pilote, conteneur, conteneur_label}`. `conteneur` est le NOM
    interne du corps ou du groupe où vit le paramètre, `''` pour la
    racine : c'est lui qui sert à décider, dans
    `profil.dans_perimetre()`. `conteneur_label` est l'étiquette du même
    conteneur, et ne sert qu'à l'affichage. `swaging` marque le VarSet d'un sertissage : par
    construction son `InnerRadius` porte le rayon d'une arête, donc il
    correspondra toujours — voir le classement dans `candidats_pilotage`.
    """
    entrees = []
    if document is None:
        return entrees

    def _valeur(brut):
        if brut is None:
            return None
        if hasattr(brut, 'Value'):
            try:
                return float(brut.Value)
            except Exception:
                return None
        try:
            return float(brut)
        except (TypeError, ValueError):
            return None

    def _expressions(objet):
        posees = {}
        for entree in (getattr(objet, 'ExpressionEngine', None) or ()):
            try:
                posees[str(entree[0]).lstrip('.')] = str(entree[1])
            except Exception:
                continue
        return posees

    internes = ('Label', 'Label2', 'Visibility', 'ExpressionEngine', 'Group',
                'Proxy', '_Body')

    # ⚠ UN RAYON NE SE COMPARE QU'À DES LONGUEURS — liste blanche, et non
    # liste noire. Le 21/09/2026, `SwagingVarSet.SwagingAngle`, qui vaut
    # **30 degrés**, a été retenu comme candidat DIAMÈTRE d'une arête de
    # **30 mm** : deux grandeurs sans rapport, égales par le seul hasard de
    # leur nombre. Les contraintes d'angle étaient déjà écartées ; les
    # propriétés d'angle ne l'étaient pas.
    #
    # Liste BLANCHE parce qu'une liste noire laisse passer ce qu'on n'a pas
    # prévu — masses, températures, pourcentages. Ce qui n'est pas une
    # longueur n'a rien à faire dans cette comparaison, connu ou non.
    #
    # `App::PropertyFloat` et `App::PropertyInteger` n'ont PAS d'unité : ils
    # sont admis parce qu'un paramétrage sans unité est courant, et qu'une
    # valeur sans unité assignée à une longueur est prise pour des
    # millimètres (mesuré le 21/09). C'est un choix, et il est ici.
    types_longueur = (
        'App::PropertyLength', 'App::PropertyDistance',
        'App::PropertyDistanceX', 'App::PropertyDistanceY',
        'App::PropertyDistanceZ', 'App::PropertyFloat',
        'App::PropertyFloatConstraint', 'App::PropertyInteger',
    )
    # Même principe pour les contraintes d'esquisse : seules celles qui
    # cotent une longueur peuvent valoir un rayon ou un diamètre.
    contraintes_longueur = ('Distance', 'DistanceX', 'DistanceY',
                            'Radius', 'Diameter')

    carte = _carte_contenance(document)
    # Le NOM interne sert à décider (le périmètre compare des noms) ;
    # l'ÉTIQUETTE sert à parler à l'utilisateur, qui ne voit qu'elle dans
    # l'arbre. Le journal désignait le même corps de deux façons —
    # `[Body001]` ici, « corps Corps » ailleurs (relevé le 21/09).
    etiquettes = {}
    for _o in document.Objects:
        try:
            etiquettes[_o.Name] = _o.Label
        except Exception:
            continue

    for objet in document.Objects:
        type_id = getattr(objet, 'TypeId', '')
        conteneur = _conteneur_lu(objet, carte)
        conteneur_label = etiquettes.get(conteneur, conteneur)

        if type_id == 'App::VarSet':
            posees = _expressions(objet)
            est_swaging = bool(prefixe_varset_swaging) and \
                objet.Name.startswith(prefixe_varset_swaging)
            for nom in (getattr(objet, 'PropertiesList', None) or ()):
                if nom in internes:
                    continue
                try:
                    type_prop = objet.getTypeIdOfProperty(nom)
                except Exception:
                    type_prop = ''
                if type_prop not in types_longueur:
                    continue
                valeur = _valeur(getattr(objet, nom, None))
                if valeur is None:
                    continue
                entrees.append({
                    'source':       'varset',
                    'chemin':       '%s.%s' % (objet.Name, nom),
                    'nom':          nom,
                    'valeur':       valeur,
                    'esquisse':     None,
                    'swaging':      est_swaging,
                    'deja_pilote':  posees.get(nom),
                    'conteneur':    conteneur,
                    'conteneur_label': conteneur_label,
                })

        elif type_id == 'Sketcher::SketchObject':
            posees = _expressions(objet)
            try:
                contraintes = list(objet.Constraints or ())
            except Exception:
                contraintes = []
            for contrainte in contraintes:
                nom = getattr(contrainte, 'Name', '') or ''
                if not nom:
                    continue
                if not getattr(contrainte, 'IsDriving', True):
                    continue
                if getattr(contrainte, 'Type', '') not in contraintes_longueur:
                    continue
                valeur = _valeur(getattr(contrainte, 'Value', None))
                if valeur is None:
                    continue
                entrees.append({
                    'source':       'contrainte',
                    'chemin':       '%s.Constraints.%s' % (objet.Name, nom),
                    'nom':          nom,
                    'valeur':       valeur,
                    'esquisse':     objet.Name,
                    'swaging':      False,
                    'deja_pilote':  posees.get('Constraints.%s' % nom),
                    'conteneur':    conteneur,
                    'conteneur_label': conteneur_label,
                })

    return entrees


def resoudre_element_selectionne():
    """Premier sous-élément de la sélection 3D, quel que soit son type.

    Différent de `resoudre_arete_selectionnee()`, qui ne retient que les
    arêtes circulaires parce qu'elle prépare une *création*. Ici on cherche
    à savoir **d'où vient** ce qui est cliqué : une face de sertissage est un
    point d'entrée aussi légitime qu'une arête.

    Rend un dictionnaire `{objet, nom_element, body}` ou None. Ne lève
    jamais.
    """
    if Gui is None:
        return None
    try:
        selection = Gui.Selection.getSelectionEx()
    except Exception:
        return None
    for sel in selection or ():
        objet = resoudre_objet_reel(sel.Object)
        if objet is None:
            continue
        noms = list(sel.SubElementNames or ())
        sous_objets = list(sel.SubObjects or ())
        for rang, nom in enumerate(noms):
            court = str(nom).split('.')[-1]
            if not court:
                continue
            # Une arête circulaire peut servir d'appui à une CRÉATION ; une
            # face, jamais. C'est ce qui rend le clic ambigu ou non.
            sous = sous_objets[rang] if rang < len(sous_objets) else None
            if sous is None and court.startswith('Edge'):
                try:
                    sous = objet.Shape.getElement(court)
                except Exception:
                    sous = None
            return {
                'objet': objet,
                'nom_element': court,
                'body': resoudre_body_depuis_objet(objet),
                'arete_possible': bool(court.startswith('Edge')
                                       and est_arete_circulaire(sous)),
            }
    return None


def support_attachement(body, objet):
    """Objet à référencer dans `AttachmentSupport`.

    Ne renvoie **jamais** le corps lui-même : l'esquisse est ajoutée dans ce
    corps, et l'y attacher créerait une dépendance circulaire. Un clic en vue
    3D sur un corps donne `sel.Object = Body`, dont la forme est celle de son
    Tip — c'est donc le Tip qu'il faut référencer, avec la même numérotation
    d'arêtes.
    """
    if body is not None and (objet is body or objet is None):
        return body.Tip
    return objet


def contexte_vue():
    """Document regardé et placement monde de l'instance sélectionnée.

    Rend `{'document': doc, 'placement': App.Placement}`, ou None si la
    sélection ne permet pas de l'établir.

    **À appeler avant toute boîte de dialogue** : un dialogue qui éclaire un
    objet écrase la sélection dont ce relevé dépend.

    ⚠ Le placement est **le chemin depuis la racine, SEUL**. Il ne se compose
    jamais avec `body.Placement` : `LinkTransform` vaut `False` par défaut,
    donc le lien **remplace** le placement du corps. Composer les deux est
    une faute, mesurée à 133,6 mm sur SpringFull le 15/09/2026. Mesuré à
    nouveau le même jour sur Swaging, où les deux formes coïncidaient — mais
    seulement parce que le corps était à l'origine.
    """
    if Gui is None:
        return None
    try:
        brut = Gui.Selection.getSelectionEx('', 0)
    except Exception:
        return None
    if not brut:
        return None
    selection = brut[0]
    tete = selection.Object
    chemins = list(selection.SubElementNames or ())
    if tete is None or not chemins:
        return None
    try:
        matrice = tete.getSubObject(chemins[0], 4)
    except Exception:
        return None
    if matrice is None:
        return None
    return {'document': tete.Document, 'placement': App.Placement(matrice)}


def arete_du_sketch(sketch):
    """Description de l'arête d'appui d'une esquisse déjà attachée.

    Sert à rouvrir un sertissage existant : le dialogue affiche l'arête, son
    rayon et son axe, et ces informations doivent venir du modèle et non
    d'une sélection qui n'a pas eu lieu.

    Rend None si l'attachement n'est pas lisible — le nom d'arête a pu
    changer avec la topologie. L'appelant affiche alors un état dégradé
    plutôt que de refuser la modification : les paramètres du sertissage,
    eux, restent parfaitement modifiables.
    """
    reference = getattr(sketch, 'AttachmentSupport', None) \
        or getattr(sketch, 'Support', None)
    if not reference:
        return None
    try:
        support, sous = reference[0]
        nom_edge = list(sous or ())[0]
        edge = support.Shape.getElement(nom_edge)
    except Exception:
        return None
    if not est_arete_circulaire(edge):
        return None
    return {
        'objet': support,
        'nom_edge': nom_edge,
        'edge': edge,
        'rayon': float(edge.Curve.Radius),
        'centre': App.Vector(edge.Curve.Center),
        'axe': App.Vector(edge.Curve.Axis),
    }


def label_disponible(document, base):
    """`base`, suffixé numériquement si un objet porte déjà ce Label."""
    if document is None:
        return base
    existants = set()
    for objet in document.Objects:
        try:
            existants.add(objet.Label)
        except Exception:
            continue
    if base not in existants:
        return base
    rang = 1
    while '%s%03d' % (base, rang) in existants:
        rang += 1
    return '%s%03d' % (base, rang)


def description_axe(vecteur):
    """Écriture courte d'un vecteur d'axe, pour l'affichage."""
    if vecteur is None:
        return '-'
    return '(%.3f, %.3f, %.3f)' % (vecteur.x, vecteur.y, vecteur.z)


def longueur_arc(rayon_sertissage, angle_degres):
    """Longueur de la partie courbe de la lèvre (mm)."""
    return float(rayon_sertissage) * math.radians(float(angle_degres))


def tolerance():
    """Tolérance géométrique utilisée par le module."""
    return _TOLERANCE_GEOM_MM
