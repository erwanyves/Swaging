# -*- coding: utf-8 -*-
"""Apparence : conservation de celle du corps, et aperçu de l'opération seule.

Deux besoins distincts, réunis ici parce qu'ils touchent tous deux au rendu.

**Conserver l'apparence du corps.** Une fonction PartDesign nouvellement créée
reçoit l'apparence par défaut, et comme elle devient le Tip du corps, c'est
elle qui s'affiche : un corps coloré repasse en gris dès qu'on lui ajoute un
sertissage. L'apparence de l'ancien Tip est donc relevée avant la création et
reposée sur la nouvelle fonction.

**Montrer l'opération, pas le corps.** Une révolution additive est fusionnée
au corps : rendre la fonction transparente rendrait tout le corps transparent.
Ce n'est pas ce qu'on veut voir. On affiche donc, pendant le réglage, la
fonction précédente telle quelle (le corps *avant* sertissage) plus un solide
temporaire portant l'`AddSubShape` de la révolution — la matière ajoutée, et
elle seule — en transparence. C'est ce que PartDesign lui-même montre pendant
l'édition d'une fonction.

Aucune exception n'est avalée : chaque échec est journalisé. Un
`except: pass` ici masquerait une propriété absente aussi bien qu'une faute de
frappe (`mecanismes_partages.md` §7).
"""

import FreeCAD as App
import Part

# Propriétés d'apparence relevées sur la vue. `DiffuseColor` est volontairement
# absente : c'est un tableau par face, intransposable d'une forme à l'autre.
_PROPRIETES_VUE = (
    'ShapeAppearance', 'ShapeColor', 'Transparency',
    'LineColor', 'PointColor', 'LineWidth', 'PointSize', 'DisplayMode',
)

# Propriété d'apparence portée par l'objet lui-même (système Materials).
_PROPRIETE_MATIERE = 'ShapeMaterial'

_NOM_APERCU = 'SwagingApercu'
_TRANSPARENCE_APERCU = 60
_COULEUR_APERCU = (0.95, 0.55, 0.10)


def _journaliser(message, erreur):
    App.Console.PrintLog('[Swaging] %s : %s\n' % (message, erreur))


# ---------------------------------------------------------------------------
# Conservation de l'apparence
# ---------------------------------------------------------------------------

def capturer(objet):
    """Relève l'apparence de `objet`. Retourne un dictionnaire, jamais None.

    Un dictionnaire vide signifie simplement qu'il n'y avait rien à relever
    (pas d'interface graphique, objet sans vue) — `appliquer()` n'aura alors
    rien à faire.
    """
    aspect = {}
    if objet is None:
        return aspect
    if hasattr(objet, _PROPRIETE_MATIERE):
        try:
            aspect[_PROPRIETE_MATIERE] = getattr(objet, _PROPRIETE_MATIERE)
        except Exception as erreur:
            _journaliser('lecture de %s' % _PROPRIETE_MATIERE, erreur)
    vue = getattr(objet, 'ViewObject', None)
    if vue is None:
        return aspect
    for nom in _PROPRIETES_VUE:
        if not hasattr(vue, nom):
            continue
        try:
            valeur = getattr(vue, nom)
        except Exception as erreur:
            _journaliser('lecture de ViewObject.%s' % nom, erreur)
            continue
        aspect[nom] = list(valeur) if nom == 'ShapeAppearance' else valeur
    return aspect


def appliquer(objet, aspect):
    """Repose une apparence relevée par `capturer()`.

    La matière est posée en premier : l'affecter réinitialise les couleurs de
    la vue, qui doivent donc être écrites après pour ne pas être écrasées.
    """
    if objet is None or not aspect:
        return
    if _PROPRIETE_MATIERE in aspect and hasattr(objet, _PROPRIETE_MATIERE):
        try:
            setattr(objet, _PROPRIETE_MATIERE, aspect[_PROPRIETE_MATIERE])
        except Exception as erreur:
            _journaliser('écriture de %s' % _PROPRIETE_MATIERE, erreur)
    vue = getattr(objet, 'ViewObject', None)
    if vue is None:
        return
    for nom in _PROPRIETES_VUE:
        if nom not in aspect or not hasattr(vue, nom):
            continue
        valeur = aspect[nom]
        if nom == 'ShapeAppearance':
            valeur = _appearance_uniforme(valeur)
            if valeur is None:
                continue
        try:
            setattr(vue, nom, valeur)
        except Exception as erreur:
            _journaliser('écriture de ViewObject.%s' % nom, erreur)


def _appearance_uniforme(valeur):
    """Ramène une `ShapeAppearance` à une forme transposable.

    Une liste de plusieurs matières décrit un coloriage par face : elle ne
    peut pas être reportée telle quelle sur une forme dont le nombre de faces
    diffère. La première matière est alors appliquée uniformément, et le fait
    est journalisé — mieux vaut la bonne couleur d'ensemble que le gris par
    défaut.
    """
    if not valeur:
        return None
    if len(valeur) == 1:
        return valeur
    App.Console.PrintLog(
        '[Swaging] apparence par face (%d matières) non transposable : la '
        'première est appliquée uniformément\n' % len(valeur))
    return [valeur[0]]


# ---------------------------------------------------------------------------
# Aperçu de l'opération seule
# ---------------------------------------------------------------------------

def _forme_ajoutee(revolution, body, placement=None):
    """Forme de la matière ajoutée, posée dans le repère demandé.

    Sans `placement`, la forme est posée dans le repère du document du corps
    — le cas mono-document, inchangé.

    Avec `placement` (le chemin depuis la racine de l'assemblage), elle est
    posée en coordonnées monde de l'assemblage. Ce placement **remplace**
    celui du corps, il ne s'y compose pas : `LinkTransform` vaut `False` par
    défaut, donc le lien remplace le placement du corps (mesuré le
    15/09/2026, 133,6 mm d'écart sur SpringFull quand on compose).

    ⚠ **`AddSubShape` est exprimée dans le repère de la FONCTION, pas dans
    celui du corps.** Le placement de la révolution s'applique donc toujours,
    quel que soit le reste de la chaîne. Mesuré le 15/09/2026 sur un corps
    dont la première esquisse n'est pas sur XY — corps à l'identité,
    fonctions à 90° autour de X :

        part du volume ajouté tombant DANS la révolution
          identité                        :  39,48 %
          body.Placement  (code d'alors)  :  39,48 %
          revolution.Placement            : 100,00 %

    Sur un corps dont la première esquisse est sur XY, les fonctions sont à
    l'identité comme le corps : tous les candidats coïncident, et le défaut
    reste invisible. Aucun corps d'essai ne pouvait donc le révéler.
    """
    forme = getattr(revolution, 'AddSubShape', None)
    if forme is None or forme.isNull():
        return None
    copie = forme.copy()
    # Repère de la fonction -> repère du corps, puis repère du corps -> monde
    # (le chemin depuis la racine en assemblage, le placement du corps
    # sinon). Les deux étages sont distincts et se composent toujours dans
    # cet ordre.
    vers_le_corps = App.Placement(revolution.Placement)
    vers_le_monde = placement if placement is not None else body.Placement
    copie.Placement = App.Placement(vers_le_monde).multiply(
        vers_le_corps).multiply(copie.Placement)
    return copie


def creer_apercu_operation(document, revolution, body, placement=None):
    """Solide temporaire montrant la matière ajoutée, en transparence.

    `document` est celui **regardé**, pas forcément celui du corps : quand le
    composant est atteint par un lien, un objet créé dans son fichier source
    n'apparaît pas dans l'assemblage — il est hors du sous-arbre du lien — et
    marque au passage le fichier du composant comme modifié pour un simple
    artifice d'affichage. `placement` porte alors la transformation vers le
    monde de l'assemblage.

    Retourne l'objet créé, ou None si la forme ajoutée n'est pas disponible
    (recalcul en échec) — l'aperçu est alors simplement absent, jamais
    bloquant.
    """
    forme = _forme_ajoutee(revolution, body, placement)
    if forme is None:
        return None
    try:
        temoin = document.addObject('Part::Feature', _NOM_APERCU)
        temoin.Label = _NOM_APERCU
        temoin.Shape = forme
    except Exception as erreur:
        _journaliser('création de l\'aperçu de l\'opération', erreur)
        return None
    vue = getattr(temoin, 'ViewObject', None)
    if vue is not None:
        for nom, valeur in (('ShapeColor', _COULEUR_APERCU),
                            ('Transparency', _TRANSPARENCE_APERCU),
                            ('Selectable', False)):
            if not hasattr(vue, nom):
                continue
            try:
                setattr(vue, nom, valeur)
            except Exception as erreur:
                _journaliser('aperçu : ViewObject.%s' % nom, erreur)
    return temoin


def majorer_apercu_operation(temoin, revolution, body, placement=None):
    """Remet à jour la forme du solide d'aperçu après un recalcul."""
    if temoin is None:
        return
    forme = _forme_ajoutee(revolution, body, placement)
    if forme is None:
        return
    try:
        temoin.Shape = forme
    except Exception as erreur:
        _journaliser('mise à jour de l\'aperçu de l\'opération', erreur)


def _lire_visibilite(objet):
    """Visibilité de l'objet, ou None si indéterminable. NE MODIFIE RIEN.

    Séparée de `_visibilite()` parce que lire et écrire dans le même geste
    est précisément ce qui a produit le défaut du 21/09 (voir
    `entrer_mode_operation`).
    """
    if objet is None:
        return None
    try:
        return bool(objet.Visibility)
    except Exception as erreur:
        _journaliser('lecture de la visibilité de %s'
                     % getattr(objet, 'Name', '?'), erreur)
        return None


def _visibilite(objet, valeur):
    if objet is None:
        return None
    try:
        avant = bool(objet.Visibility)
        objet.Visibility = bool(valeur)
        return avant
    except Exception as erreur:
        _journaliser('visibilité de %s' % getattr(objet, 'Name', '?'), erreur)
        return None


def entrer_mode_operation(revolution, tip=None):
    """Masque le résultat fusionné et réaffiche le corps d'avant sertissage.

    Sans cela, le solide d'aperçu serait noyé dans la matière du résultat —
    transparent par-dessus opaque ne se voit pas. Retourne l'état de
    visibilité à restaurer.

    **`tip` est nécessaire dès que le sertissage n'est pas la dernière
    opération du corps.** À la création, la révolution EST le Tip et la
    masquer suffit. Rouvert sur un sertissage suivi d'un congé, c'est le Tip
    qui s'affiche : masquer la seule révolution ne montre rien, et le témoin
    reste noyé dans le résultat opaque. Omettre `tip` conserve l'ancien
    comportement, exact dans ce seul cas.
    """
    base = getattr(revolution, 'BaseFeature', None)
    autre_tip = tip if (tip is not None and tip is not revolution) else None

    # ⚠ RELEVER LES TROIS ÉTATS AVANT D'EN MODIFIER UN SEUL.
    #
    # Dans un `PartDesign::Body`, **rendre une fonction visible en masque
    # les autres** : c'est FreeCAD qui le fait, pas nous. La version
    # précédente relevait et modifiait dans le même dictionnaire, donc
    # dans cet ordre : révolution, puis `base` rendue VISIBLE — ce qui
    # masquait le Tip au passage — puis seulement le Tip, dont l'état
    # « d'avant » était déjà faux. `quitter_mode_operation()` restaurait
    # alors fidèlement un masquage, et le filet `retablir_tip()` devait
    # rattraper.
    #
    # Mesuré le 21/09/2026 par les jalons, sur un corps dont le Tip est un
    # congé : « entrée Fillet=visible | après entrée mode opération
    # (tip relevé=False, apercu=oui) Fillet=masqué ». Le Tip était visible
    # une ligne plus tôt, et l'état relevé disait déjà « masqué ».
    #
    # Règle générale : quand les objets d'un ensemble interagissent, on
    # relève l'ensemble, puis on écrit. Jamais en alternance.
    etat = {
        'revolution': _lire_visibilite(revolution),
        'base': _lire_visibilite(base),
        'objet_base': base,
        'tip': _lire_visibilite(autre_tip),
        'objet_tip': autre_tip,
    }
    _visibilite(revolution, False)
    _visibilite(base, True)
    _visibilite(autre_tip, False)
    return etat


def quitter_mode_operation(revolution, etat):
    """Rétablit les visibilités relevées par `entrer_mode_operation()`.

    L'ordre — Tip, puis base, puis révolution — n'est pas indifférent, pour
    la même raison qu'à l'entrée : chaque mise en visibilité en masque une
    autre. Les trois états étant écrits explicitement, le dernier écrit sur
    chaque objet est celui qui compte, et l'état final est exact quel que
    soit l'état de départ.
    """
    if not etat:
        return
    if etat.get('tip') is not None:
        _visibilite(etat.get('objet_tip'), etat['tip'])
    if etat.get('base') is not None:
        _visibilite(etat.get('objet_base'), etat['base'])
    if etat.get('revolution') is not None:
        _visibilite(revolution, etat['revolution'])
    else:
        _visibilite(revolution, True)


def tip_visible(body):
    """Vrai si le Tip du corps est affiché, None si indéterminable.

    À relever **à l'entrée** de la macro : c'est l'état auquel l'utilisateur
    s'attend à retrouver son document en sortie.
    """
    tip = getattr(body, 'Tip', None)
    if tip is None:
        return None
    try:
        return bool(tip.Visibility)
    except Exception as erreur:
        _journaliser('lecture de la visibilité du Tip', erreur)
        return None


# Jalons de visibilité du Tip, par corps : [(étape, nom du Tip, visible)].
# Diagnostic pur — rien ici ne change le document. Le but est de répondre
# à UNE question restée ouverte depuis l'écriture du filet : à quel moment
# le Tip est-il masqué ? Signalé quatre fois par l'utilisateur le 21/09.
_JALONS = {}


def oublier_jalons(body):
    """Vide la trace du corps. À appeler à l'entrée de la macro."""
    _JALONS.pop(getattr(body, 'Name', '?'), None)


def jalonner_tip(body, etape):
    """Relève la visibilité du Tip à cette étape, et la retourne.

    Le **nom** du Tip est relevé lui aussi : un Tip qui CHANGE en cours de
    route — une création en pose un nouveau — et un Tip qu'on MASQUE ne se
    soignent pas de la même façon, et le seul message d'arrivée ne permet
    pas de les distinguer.
    """
    visible = tip_visible(body)
    tip = getattr(body, 'Tip', None)
    _JALONS.setdefault(getattr(body, 'Name', '?'), []).append(
        (etape, getattr(tip, 'Name', '?'), visible))
    return visible


def _trace_jalons(body):
    """Les jalons en clair, et l'intervalle où la visibilité a basculé."""
    jalons = _JALONS.get(getattr(body, 'Name', '?')) or []
    if not jalons:
        return []
    lisible = ' | '.join(
        '%s %s=%s' % (etape, nom,
                      'visible' if vu else ('masqué' if vu is False
                                            else 'indéterminé'))
        for etape, nom, vu in jalons)
    lignes = ['[Swaging]   jalons : %s\n' % lisible]
    bascule = None
    for precedent, courant in zip(jalons, jalons[1:]):
        if precedent[2] and courant[2] is False:
            bascule = (precedent, courant)
    if bascule is not None:
        (etape_a, tip_a, _), (etape_b, tip_b, _) = bascule
        if tip_a != tip_b:
            lignes.append(
                '[Swaging]   -> le Tip a CHANGÉ entre « %s » (%s) et '
                '« %s » (%s) : ce n\'est pas un masquage.\n'
                % (etape_a, tip_a, etape_b, tip_b))
        else:
            lignes.append(
                '[Swaging]   -> %s masqué entre « %s » et « %s ».\n'
                % (tip_a, etape_a, etape_b))
    else:
        lignes.append('[Swaging]   -> aucun jalon ne montre la bascule : '
                      'elle a eu lieu hors des points relevés.\n')
    return lignes


def retablir_tip(body, avant):
    """Réaffiche le Tip du corps s'il l'était à l'entrée. Vrai si corrigé.

    Invariant de sortie, et non réparation d'un cas précis : le Tip peut
    avoir changé en cours de route (une création en pose un nouveau), avoir
    été masqué par le mode « opération seule », ou l'avoir été par FreeCAD
    lui-même en défaisant l'ajout d'une fonction.

    **Chaque correction est journalisée en avertissement.** Un rétablissement
    silencieux rendrait la cause introuvable : c'est précisément le défaut
    que ce correctif ne doit pas reproduire.
    """
    if not avant:
        return False
    tip = getattr(body, 'Tip', None)
    if tip is None:
        return False
    try:
        if bool(tip.Visibility):
            return False
        tip.Visibility = True
    except Exception as erreur:
        _journaliser('rétablissement de la visibilité du Tip', erreur)
        return False
    App.Console.PrintWarning(
        '[Swaging] le Tip %s du corps %s était masqué en sortie de macro : '
        'réaffiché.\n'
        % (getattr(tip, 'Name', '?'), getattr(body, 'Name', '?')))
    for ligne in _trace_jalons(body):
        App.Console.PrintWarning(ligne)
    return True


def nom_apercu():
    """Nom interne du solide d'aperçu, pour le nettoyage à l'annulation."""
    return _NOM_APERCU
