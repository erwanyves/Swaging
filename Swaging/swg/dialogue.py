# -*- coding: utf-8 -*-
"""Interface de la macro Swaging.

Aucun dialogue n'est modal : `QDialog.exec_()` est ApplicationModal et bloque
les événements de repeinture de la vue 3D — la vue devient inerte et toute
sélection en cours de dialogue est impossible. Les dialogues sont donc
affichés par `show()` et l'attente est faite par une `QEventLoop` locale, qui
bloque le script appelant sans bloquer FreeCAD.
"""

import FreeCAD as App
import FreeCADGui as Gui

from . import aspect
from . import geometrie
from . import i18n
from . import profil

try:
    from PySide import QtCore, QtWidgets
except ImportError:  # pragma: no cover - dépend de la version de FreeCAD
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets

_ACCEPTE = 1

# Sentinelle : « l'utilisateur veut un nouveau sertissage ». Un objet dédié
# plutôt que None, qui signifie déjà « il a renoncé ».
_CREER = object()

_UNITES = {
    'App::PropertyLength': ' mm',
    'App::PropertyAngle': ' °',
}

_BORNES = {
    'App::PropertyLength': (0.001, 1.0e6),
    'App::PropertyAngle': (0.001, 179.999),
}


# ---------------------------------------------------------------------------
# Compatibilité Qt5 / Qt6
# ---------------------------------------------------------------------------

def _executer(objet):
    """Appelle `exec_()` ou `exec()` selon la liaison Qt disponible."""
    methode = getattr(objet, 'exec_', None)
    if methode is None:
        methode = getattr(objet, 'exec')
    return methode()


def _message(titre, texte, erreur=False):
    """Boîte d'information non bloquante pour la vue 3D."""
    boite = QtWidgets.QMessageBox(Gui.getMainWindow())
    boite.setWindowTitle(titre)
    boite.setText(texte)
    boite.setIcon(QtWidgets.QMessageBox.Critical if erreur
                  else QtWidgets.QMessageBox.Information)
    boite.setWindowFlags(boite.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    _executer(boite)


def _afficher_non_modal(dialogue):
    """Affiche `dialogue` sans bloquer la vue 3D, et attend sa fermeture."""
    boucle = QtCore.QEventLoop()
    dialogue.finished.connect(lambda _code: boucle.quit())
    dialogue.setModal(False)
    dialogue.setWindowFlags(dialogue.windowFlags()
                            | QtCore.Qt.Tool
                            | QtCore.Qt.WindowStaysOnTopHint)
    dialogue.show()
    dialogue.raise_()
    dialogue.activateWindow()
    _executer(boucle)
    return dialogue.result()


# ---------------------------------------------------------------------------
# Sélection d'une arête en vue 3D
# ---------------------------------------------------------------------------

class _ObservateurSelection(object):
    """Observateur de sélection appelant `rappel` à chaque ajout."""

    def __init__(self, rappel):
        self._rappel = rappel

    def addSelection(self, _document, _objet, _sous_element, _point):
        self._rappel()


class _FenetreAttente(QtWidgets.QWidget):
    """Petite fenêtre flottante affichée pendant l'attente d'un clic 3D."""

    def __init__(self, sortie):
        super(_FenetreAttente, self).__init__(Gui.getMainWindow())
        self._sortie = sortie
        self._termine = False
        self.setWindowTitle(i18n.tr('sel.titre'))
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.WindowStaysOnTopHint)
        disposition = QtWidgets.QVBoxLayout(self)
        etiquette = QtWidgets.QLabel(i18n.tr('sel.instruction'))
        etiquette.setWordWrap(True)
        disposition.addWidget(etiquette)
        bouton = QtWidgets.QPushButton(i18n.tr('sel.annuler'))
        bouton.clicked.connect(self.terminer)
        disposition.addWidget(bouton)

    def terminer(self):
        """Sort de l'attente une seule fois, quel que soit le chemin."""
        if self._termine:
            return
        self._termine = True
        self._sortie()

    def closeEvent(self, evenement):
        self.terminer()
        super(_FenetreAttente, self).closeEvent(evenement)


def demander_arete():
    """Attend qu'une arête circulaire soit cliquée en vue 3D.

    Retourne le descriptif de l'arête, ou None si l'utilisateur annule.
    """
    resultat = {'arete': None}
    boucle = QtCore.QEventLoop()
    fenetre = _FenetreAttente(boucle.quit)

    def _sur_selection():
        arete = geometrie.resoudre_arete_selectionnee()
        if arete is None:
            return  # sélection non exploitable : on continue d'attendre
        resultat['arete'] = arete
        fenetre.terminer()

    observateur = _ObservateurSelection(_sur_selection)
    Gui.Selection.addObserver(observateur)
    fenetre.show()
    try:
        _executer(boucle)
    finally:
        try:
            Gui.Selection.removeObserver(observateur)
        except Exception:
            pass
        fenetre.close()
    return resultat['arete']


# ---------------------------------------------------------------------------
# Dialogue principal
# ---------------------------------------------------------------------------

class DialogueSwaging(QtWidgets.QDialog):
    """Réglage des paramètres, avec aperçu en direct dans la vue 3D.

    Le sertissage est **déjà construit** quand ce dialogue s'ouvre : chaque
    changement de valeur écrit dans le VarSet et recalcule, l'utilisateur voit
    donc le résultat réel et non une approximation. C'est ce qui rend la case
    « inverser le sens » utilisable — on ne peut pas décider d'inverser ce
    qu'on ne voit pas.

    L'annulation défait la création (transaction abandonnée par l'appelant),
    donc rien ne reste dans le document.
    """

    def __init__(self, arete, body, support, data, varset, sketch, revolution,
                 parent=None, modification=False, vue=None):
        super(DialogueSwaging, self).__init__(parent or Gui.getMainWindow())
        self.modification = bool(modification)
        self.arete = arete
        self.body = body
        self.support = support
        self.data = data
        self.varset = varset
        self.sketch = sketch
        self.revolution = revolution
        self.document = body.Document
        # Le solide d'aperçu naît dans le document REGARDÉ. Quand le corps
        # est atteint par un lien, ce n'est pas le sien : un objet créé dans
        # le fichier source est hors du sous-arbre du lien, donc invisible
        # dans l'assemblage — et il y marquerait le fichier du composant
        # comme modifié pour un simple artifice d'affichage.
        vue_document = (vue or {}).get('document')
        if vue_document is not None and vue_document is not self.document:
            self._document_temoin = vue_document
            self._placement_temoin = (vue or {}).get('placement')
        else:
            self._document_temoin = self.document
            self._placement_temoin = None
        self.champs = {}
        self.pilotes = {}
        self._apercu_en_cours = False
        self._temoin = None
        self._etat_visibilite = None
        self.setWindowTitle(i18n.tr('dlg.titre'))

        # Les changements de valeur sont regroupés : taper « 12.5 » dans un
        # champ produit plusieurs signaux, un seul recalcul suffit.
        self._minuterie = QtCore.QTimer(self)
        self._minuterie.setSingleShot(True)
        self._minuterie.setInterval(250)
        self._minuterie.timeout.connect(self.appliquer_apercu)

        disposition = QtWidgets.QVBoxLayout(self)
        disposition.addWidget(self._groupe_arete())
        disposition.addWidget(self._groupe_parametres())
        disposition.addWidget(self._groupe_options())
        self.etiquette_alerte = QtWidgets.QLabel('')
        self.etiquette_alerte.setWordWrap(True)
        self.etiquette_alerte.setStyleSheet('color: #c0392b;')
        self.etiquette_alerte.hide()
        disposition.addWidget(self.etiquette_alerte)
        disposition.addWidget(self._boutons())
        self._connecter_apercu()
        if self.case_transparence.isChecked():
            self._entrer_mode_operation()

    # -- construction de l'interface ---------------------------------------

    def _groupe_arete(self):
        groupe = QtWidgets.QGroupBox(i18n.tr('dlg.groupe_arete'))
        formulaire = QtWidgets.QFormLayout(groupe)
        formulaire.addRow(i18n.tr('info.corps'),
                          QtWidgets.QLabel(self.body.Label))
        formulaire.addRow(i18n.tr('info.support'),
                          QtWidgets.QLabel(getattr(self.support, 'Label',
                                                   '-')))
        formulaire.addRow(i18n.tr('info.arete'),
                          QtWidgets.QLabel(self.arete['nom_edge']))
        formulaire.addRow(i18n.tr('info.rayon'),
                          QtWidgets.QLabel('%.4f mm' % self.arete['rayon']))
        formulaire.addRow(i18n.tr('info.axe'),
                          QtWidgets.QLabel(
                              geometrie.description_axe(self.arete['axe'])))
        return groupe

    def _figer_champ_pilote(self, champ, expression):
        """Rend un champ piloté GRISÉ et non saisissable.

        `setEnabled(False)` et non `setReadOnly(True)` : c'est Qt qui
        applique alors la palette « désactivé » du thème en place, donc
        aucune couleur écrite en dur — ce qui resterait lisible en thème
        clair et illisible en thème sombre.

        Avant ce correctif le champ acceptait la frappe et
        `profil.appliquer_valeurs()` sautait ensuite l'écriture : la
        valeur saisie disparaissait sans explication. Le champ dit
        désormais ce que le modèle fait déjà.
        """
        champ.setEnabled(False)
        champ.setToolTip(i18n.tr('param.pilote_aide', source=expression))

    def _ligne_pilotee(self, champ, expression):
        """Le champ grisé, suivi de sa source EN CLAIR.

        La source ne vit pas seulement dans l'infobulle : une infobulle
        ne se lit que si l'on sait qu'elle est là. Décision (c) du
        21/09 : « champ grisé, source affichée ».
        """
        conteneur = QtWidgets.QWidget(self)
        disposition = QtWidgets.QHBoxLayout(conteneur)
        disposition.setContentsMargins(0, 0, 0, 0)
        disposition.addWidget(champ)
        etiquette = QtWidgets.QLabel(
            i18n.tr('param.pilote', source=expression), conteneur)
        etiquette.setStyleSheet('color: #888;')
        etiquette.setToolTip(i18n.tr('param.pilote_aide',
                                     source=expression))
        disposition.addWidget(etiquette, 1)
        return conteneur

    def _groupe_parametres(self):
        groupe = QtWidgets.QGroupBox(i18n.tr('dlg.groupe_params'))
        formulaire = QtWidgets.QFormLayout(groupe)
        # Les valeurs affichées sont celles du MODÈLE, relues sur le VarSet.
        # En création il vient d'être posé aux valeurs de référence avec le
        # rayon de l'arête : les deux modes empruntent donc le même chemin.
        courantes = profil.valeurs_courantes(self.varset, self.data)
        # Les paramètres portés par une expression : ni saisissables,
        # ni réinitialisables. Vaut en modification ET en création,
        # puisque la liaison est posée avant l'ouverture du dialogue.
        self.pilotes = profil.expressions_pilotes(self.varset)
        for descripteur in profil.parametres(self.data):
            nom = descripteur['nom']
            type_propriete = descripteur['type']
            champ = QtWidgets.QDoubleSpinBox(self)
            champ.setDecimals(3)
            mini, maxi = _BORNES.get(type_propriete, (0.0, 1.0e6))
            valeur = courantes.get(nom, float(descripteur['defaut']))
            # ⚠ `setRange()` fait ÉCRÊTER `setValue()` EN SILENCE. À la
            # réouverture d'un sertissage, la valeur vient du modèle : si
            # elle sortait des bornes, elle serait écrêtée à l'affichage
            # puis RÉÉCRITE écrêtée à la validation — le modèle changerait
            # sans que personne ne l'ait demandé. La plage s'élargit donc à
            # ce que le modèle porte réellement (leçon du 15/09/2026).
            mini = min(mini, valeur)
            maxi = max(maxi, valeur)
            champ.setRange(mini, maxi)
            champ.setSuffix(_UNITES.get(type_propriete, ''))
            champ.setSingleStep(0.1)
            champ.setValue(valeur)
            champ.setToolTip(i18n.tr(descripteur['doc_cle']))
            self.champs[nom] = champ
            expression = self.pilotes.get(nom)
            if expression:
                self._figer_champ_pilote(champ, expression)
                formulaire.addRow(i18n.tr('param.%s' % nom),
                                  self._ligne_pilotee(champ, expression))
            else:
                formulaire.addRow(i18n.tr('param.%s' % nom), champ)
        bouton = QtWidgets.QPushButton(i18n.tr('champ.reinit'))
        bouton.clicked.connect(self.reinitialiser)
        formulaire.addRow('', bouton)
        return groupe

    def _groupe_options(self):
        groupe = QtWidgets.QGroupBox(i18n.tr('dlg.groupe_options'))
        formulaire = QtWidgets.QFormLayout(groupe)
        self.case_inverser = QtWidgets.QCheckBox(i18n.tr('champ.inverser'))
        self.case_inverser.setToolTip(i18n.tr('champ.inverser_aide'))
        # État relu sur l'esquisse : en création elle vient d'être posée au
        # sens droit, à la réouverture elle porte le sens réellement en
        # place. La case est cochée AVANT `_connecter_apercu()`, donc sans
        # déclencher de recalcul parasite.
        self.case_inverser.setChecked(profil.sens_inverse(self.sketch))
        formulaire.addRow('', self.case_inverser)
        self.case_apercu = QtWidgets.QCheckBox(i18n.tr('champ.apercu'))
        self.case_apercu.setToolTip(i18n.tr('champ.apercu_aide'))
        self.case_apercu.setChecked(True)
        formulaire.addRow('', self.case_apercu)
        self.case_transparence = QtWidgets.QCheckBox(
            i18n.tr('champ.transparence'))
        self.case_transparence.setToolTip(i18n.tr('champ.transparence_aide'))
        self.case_transparence.setChecked(True)
        formulaire.addRow('', self.case_transparence)
        # L'état serti / non serti. Deux boutons RADIO et non une case :
        # ce sont deux représentations de la même pièce, et chaque
        # libellé se lit sans avoir à déduire l'autre.
        self.radio_serti = QtWidgets.QRadioButton(i18n.tr('champ.serti'))
        self.radio_non_serti = QtWidgets.QRadioButton(
            i18n.tr('champ.non_serti'))
        self.radio_serti.setToolTip(i18n.tr('champ.serti_aide'))
        self.radio_non_serti.setToolTip(i18n.tr('champ.non_serti_aide'))
        self._boutons_etat = QtWidgets.QButtonGroup(self)
        self._boutons_etat.addButton(self.radio_serti)
        self._boutons_etat.addButton(self.radio_non_serti)
        # État relu sur le MODÈLE, comme le sens d'insertion : en
        # création il vient d'être posé à « serti », à la réouverture il
        # porte l'état réellement en place. Coché AVANT
        # `_connecter_apercu()`, donc sans recalcul parasite.
        serti = profil.etat_serti(self.varset, self.data)
        self.radio_serti.setChecked(serti)
        self.radio_non_serti.setChecked(not serti)
        if not profil.etat_disponible(self.varset, self.data):
            # Le VarSet ne porte pas la propriété et la mise à niveau
            # n'a pas abouti : un bouton qui n'agirait sur rien se
            # GRISE, et son infobulle dit pourquoi.
            self.radio_serti.setEnabled(False)
            self.radio_non_serti.setEnabled(False)
            for _bouton in (self.radio_serti, self.radio_non_serti):
                _bouton.setToolTip(i18n.tr('champ.etat_indisponible'))
        formulaire.addRow(i18n.tr('champ.etat'), self.radio_serti)
        formulaire.addRow('', self.radio_non_serti)
        # Le VarSet existe déjà (il porte l'aperçu) : le champ montre son
        # Label réel. Appeler label_disponible() ici renverrait un nom
        # suffixé, puisque le nom de base est justement déjà pris — par
        # l'objet que ce champ sert à renommer.
        self.champ_nom = QtWidgets.QLineEdit(self.varset.Label)
        formulaire.addRow(i18n.tr('champ.nom_varset'), self.champ_nom)
        return groupe

    def _boutons(self):
        boite = QtWidgets.QDialogButtonBox(self)
        self.bouton_creer = boite.addButton(
            i18n.tr('btn.modifier' if self.modification else 'btn.creer'),
            QtWidgets.QDialogButtonBox.AcceptRole)
        boite.addButton(i18n.tr('btn.annuler'),
                        QtWidgets.QDialogButtonBox.RejectRole)
        boite.accepted.connect(self.valider)
        boite.rejected.connect(self.reject)
        return boite

    # -- aperçu en direct ---------------------------------------------------

    def _connecter_apercu(self):
        """Branche les champs sur la minuterie d'aperçu."""
        for champ in self.champs.values():
            champ.valueChanged.connect(self._planifier_apercu)
        self.case_inverser.toggled.connect(self._planifier_apercu)
        self.radio_serti.toggled.connect(self._planifier_apercu)
        self.case_apercu.toggled.connect(self._sur_bascule_apercu)
        self.case_transparence.toggled.connect(self._sur_bascule_transparence)

    def _planifier_apercu(self, *_args):
        """Regroupe les changements rapprochés en un seul recalcul."""
        if self.case_apercu.isChecked():
            self._minuterie.start()

    def _sur_bascule_apercu(self, actif):
        """Reprend l'aperçu à la réactivation, le gèle sinon."""
        if actif:
            self.etiquette_alerte.hide()
            self.appliquer_apercu()
        else:
            self._minuterie.stop()
            self.etiquette_alerte.setText(i18n.tr('champ.apercu_fige'))
            self.etiquette_alerte.show()

    def _entrer_mode_operation(self):
        """Affiche le corps d'avant sertissage plus la matière ajoutée seule."""
        if self._temoin is not None:
            return
        self._etat_visibilite = aspect.entrer_mode_operation(
            self.revolution, getattr(self.body, 'Tip', None))
        self._temoin = aspect.creer_apercu_operation(
            self._document_temoin, self.revolution, self.body,
            self._placement_temoin)
        # Diagnostic : l'état RELEVÉ compte autant que l'état observé. S'il
        # vaut déjà « masqué », c'est qu'on entre une deuxième fois sans
        # être ressorti — et le rétablissement restaurera fidèlement un
        # masquage. `apercu` dit si le solide témoin a pu être créé : quand
        # il ne l'est pas, la garde d'entrée ne garde plus rien.
        aspect.jalonner_tip(
            self.body,
            'après entrée mode opération (tip relevé=%s, apercu=%s)'
            % (self._etat_visibilite.get('tip'),
               'oui' if self._temoin is not None else 'NON'))
        self._recalculer()
        aspect.jalonner_tip(self.body, 'après recompute du mode opération')

    def _quitter_mode_operation(self):
        """Supprime le solide d'aperçu et rétablit les visibilités.

        Appelée aussi bien à la validation qu'à l'annulation : ce solide est
        un artifice d'affichage, il ne doit jamais subsister dans le document.
        """
        aspect.jalonner_tip(self.body, 'avant rétablissement')
        if self._temoin is not None:
            try:
                self._document_temoin.removeObject(self._temoin.Name)
            except Exception as erreur:
                App.Console.PrintWarning(
                    '[Swaging] suppression de l\'aperçu : %s\n' % erreur)
            self._temoin = None
        aspect.quitter_mode_operation(self.revolution, self._etat_visibilite)
        aspect.jalonner_tip(self.body, 'après rétablissement')
        self._etat_visibilite = None
        self._recalculer()

    def _sur_bascule_transparence(self, actif):
        """Entre ou sort du mode de représentation de l'opération seule."""
        if actif:
            self._entrer_mode_operation()
        else:
            self._quitter_mode_operation()
        Gui.updateGui()

    def _recalculer(self):
        """Recalcule le document du corps, et celui de la vue s'il diffère."""
        self.document.recompute()
        if self._document_temoin is not self.document:
            self._document_temoin.recompute()

    def nom_temoin(self):
        """Nom du solide d'aperçu s'il existe encore, pour le nettoyage."""
        return getattr(self._temoin, 'Name', None)

    def document_temoin(self):
        """Document où vit le solide d'aperçu — pas toujours celui du corps."""
        return self._document_temoin

    def _signaler(self, texte):
        """Affiche ou efface l'avertissement sous les champs."""
        if texte:
            self.etiquette_alerte.setText(texte)
            self.etiquette_alerte.show()
        else:
            self.etiquette_alerte.clear()
            self.etiquette_alerte.hide()
        self.bouton_creer.setEnabled(not texte)

    def appliquer_apercu(self):
        """Écrit les valeurs courantes dans le modèle et rafraîchit la vue.

        Une saisie incohérente n'est **jamais** poussée jusqu'au solveur : le
        message s'affiche sous les champs, le bouton de validation se
        désactive, et le modèle garde son dernier état valide.
        """
        if self._apercu_en_cours or not self.case_apercu.isChecked():
            return
        problemes = profil.verifier_valeurs(self.valeurs(), self.serti())
        if problemes:
            cle, arguments = problemes[0]
            self._signaler(i18n.tr(cle, **arguments))
            return
        self._signaler('')
        self._apercu_en_cours = True
        try:
            profil.regler_sens(self.sketch, self.inverser())
            profil.appliquer_etat(self.varset, self.data, self.serti())
            profil.appliquer_valeurs(self.varset, self.valeurs())
            self.document.recompute()
            aspect.majorer_apercu_operation(self._temoin, self.revolution,
                                            self.body,
                                            self._placement_temoin)
            self._recalculer()
            QtWidgets.QApplication.processEvents()
            Gui.updateGui()
        except Exception as erreur:
            App.Console.PrintWarning('[Swaging] %s\n' % erreur)
            self._signaler(i18n.tr('msg.echec_apercu', erreur=erreur))
        finally:
            self._apercu_en_cours = False

    # -- comportement -------------------------------------------------------

    def reinitialiser(self):
        """Remet les champs aux valeurs du modèle de référence.

        Le rayon intérieur revient au rayon mesuré sur l'arête, pas à la
        valeur du modèle : c'est lui l'entrée de la macro.
        """
        nom_rayon = profil.nom_parametre_rayon(self.data)
        for nom, valeur in profil.valeurs_reference(self.data).items():
            if nom not in self.champs:
                continue
            # Un champ piloté n'est pas réinitialisé : sa valeur vient
            # de son expression, et `appliquer_valeurs()` refuserait de
            # l'écrire. Le remettre afficherait un chiffre que la
            # validation n'appliquerait pas.
            if nom in getattr(self, 'pilotes', {}):
                continue
            self.champs[nom].setValue(
                float(self.arete['rayon']) if nom == nom_rayon
                else float(valeur))
        self._planifier_apercu()

    def valeurs(self):
        """Valeurs saisies, par nom de paramètre."""
        return dict((nom, champ.value()) for nom, champ in self.champs.items())

    def inverser(self):
        """Vrai si le sens d'insertion doit être retourné."""
        return bool(self.case_inverser.isChecked())

    def serti(self):
        """Vrai si la pièce doit être représentée sertie.

        Un seul des deux boutons est lu : ils sont exclusifs, et lire le
        second permettrait deux réponses contradictoires.
        """
        return bool(self.radio_serti.isChecked())

    def nom_varset(self):
        """Label demandé pour le VarSet, jamais vide."""
        return self.champ_nom.text().strip() or self.data['varset']['label']

    def valider(self):
        """Contrôle de cohérence, puis application définitive avant fermeture.

        L'aperçu peut être en attente (minuterie non échue) ou désactivé : les
        valeurs sont donc réappliquées ici, sans passer par la minuterie, pour
        que ce qui est conservé soit bien ce qui est affiché.
        """
        problemes = profil.verifier_valeurs(self.valeurs(), self.serti())
        if problemes:
            cle, arguments = problemes[0]
            _message(i18n.tr('dlg.titre'), i18n.tr(cle, **arguments),
                     erreur=True)
            return
        self._minuterie.stop()
        try:
            profil.regler_sens(self.sketch, self.inverser())
            profil.appliquer_etat(self.varset, self.data, self.serti())
            profil.appliquer_valeurs(self.varset, self.valeurs())
            self.varset.Label = self.nom_varset()
            self.document.recompute()
        except Exception as erreur:
            App.Console.PrintError('[Swaging] %s\n' % erreur)
            _message(i18n.tr('dlg.titre'),
                     i18n.tr('msg.erreur', erreur=erreur), erreur=True)
            return
        self._quitter_mode_operation()
        aspect.jalonner_tip(self.body, 'sortie du mode opération')
        self.accept()

    def reject(self):
        """Retire l'artifice d'affichage avant de rendre la main."""
        self._minuterie.stop()
        self._quitter_mode_operation()
        aspect.jalonner_tip(self.body, 'sortie du mode opération')
        super(DialogueSwaging, self).reject()


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def _retirer(document, nom):
    """Supprime un objet par son nom s'il est encore là. Ne lève jamais."""
    if document is None or not nom or document.getObject(nom) is None:
        return
    try:
        document.removeObject(nom)
        document.recompute()
    except Exception as erreur:
        App.Console.PrintWarning('[Swaging] suppression de %s : %s\n'
                                 % (nom, erreur))


def _defaire(document, noms):
    """Défait la création après annulation, et vérifie qu'il ne reste rien.

    L'abandon de transaction suffit normalement. Le balayage qui suit est une
    ceinture de sécurité : un objet qui survivrait resterait orphelin dans le
    document de l'utilisateur, ce qui n'est jamais acceptable pour un simple
    aperçu. Les objets sont repris **par leur nom** — après l'abandon, les
    références Python pointent des objets supprimés.
    """
    try:
        document.abortTransaction()
    except Exception as erreur:
        App.Console.PrintWarning('[Swaging] abandon de transaction : %s\n'
                                 % erreur)
    restants = [nom for nom in noms if document.getObject(nom) is not None]
    for nom in restants:
        try:
            document.removeObject(nom)
        except Exception as erreur:
            App.Console.PrintWarning('[Swaging] suppression de %s : %s\n'
                                     % (nom, erreur))
    if restants:
        document.recompute()


def _libelle_sertissage(revolution):
    """Ligne de liste d'un sertissage : son nom ET ce qui le distingue.

    Deux sertissages du même corps portent des labels voisins
    (`Swaging`, `Swaging001`) : le nom seul ne dit pas lequel est lequel. Le
    diamètre intérieur, lu sur le VarSet, le dit — et le nom du VarSet donne
    le point d'entrée si l'utilisateur veut vérifier dans l'arbre.
    """
    label = getattr(revolution, 'Label', '?')
    varset = profil.varset_du_sertissage(revolution)
    if varset is None:
        return label
    try:
        data = profil.charger()
        rayon = profil.valeurs_courantes(varset, data).get(
            profil.nom_parametre_rayon(data))
    except Exception:
        rayon = None
    if rayon is None:
        return '%s  (%s)' % (label, varset.Label)
    # Le VarSet porte un RAYON (`InnerRadius`) ; la liste annonce un
    # diamètre — c'est le vocabulaire des modèles, cotés en Ø
    # (`diametreSertissage`, `Dint`). Le doublement se fait ici et non
    # dans la chaîne traduite : une chaîne d'interface ne calcule pas.
    return i18n.tr('choix.entree', nom=label,
                   diametre=float(rayon) * 2.0,
                   varset=varset.Label)


class _DialogueChoixSertissage(QtWidgets.QDialog):
    """Liste des sertissages désignés, éclairés dans la vue 3D.

    Le survol **et** le changement de ligne allument l'objet : le survol
    pour explorer sans s'engager, le changement de ligne pour que la ligne
    courante corresponde toujours à ce qui est allumé — sans quoi un
    déplacement au clavier choisirait un objet jamais montré.

    Deux écarts délibérés avec la liste de SpringFull, dont ce mécanisme est
    transposé (`SpringFullDialogsModule.py`, `select_object()` /
    `on_item_highlighted()`) :

    - **la caméra n'est pas recadrée** (pas de `viewSelection()`). Ici
      l'utilisateur vient de cliquer l'objet : il est déjà sous ses yeux, et
      déplacer la vue à chaque survol gênerait au lieu d'aider ;
    - la dernière ligne, « créer un nouveau sertissage », n'est pas un objet
      FreeCAD : elle **éteint** la surbrillance au lieu d'allumer quoi que
      ce soit. Sans cela, elle laisserait allumé l'objet précédent et
      donnerait à croire qu'il est concerné.

    ⚠ Limite connue : `addSelection(objet)` n'allume rien à travers un
    `App::Link` — l'adressage y est `(document actif, objet de tête,
    chemin)`. En assemblage lié, la liste reste utilisable, mais muette dans
    la vue.
    """

    def __init__(self, candidats, texte, creation_possible=True,
                 parent=None):
        super(_DialogueChoixSertissage, self).__init__(
            parent or Gui.getMainWindow())
        self.candidats = list(candidats)
        # La création n'est offerte que si l'élément cliqué peut lui servir
        # d'appui — c'est-à-dire s'il s'agit d'une arête circulaire. Offrir
        # « créer sur cette arête » après un clic sur une FACE annonçait une
        # arête qui n'existait pas (signalé le 15/09/2026).
        self.creation_possible = bool(creation_possible)
        self._esquisses = [profil.esquisse_du_sertissage(objet)
                           for objet in self.candidats]
        self._visibilite_avant = {}
        self.setWindowTitle(i18n.tr('app.titre'))
        self.setMinimumWidth(460)

        disposition = QtWidgets.QVBoxLayout(self)
        etiquette = QtWidgets.QLabel(texte)
        etiquette.setWordWrap(True)
        disposition.addWidget(etiquette)

        aide = QtWidgets.QLabel('<i>%s</i>' % i18n.tr('choix.survol_aide'))
        aide.setStyleSheet('color: #888;')
        disposition.addWidget(aide)

        self.liste = QtWidgets.QListWidget(self)
        for objet in self.candidats:
            self.liste.addItem(_libelle_sertissage(objet))
        if self.creation_possible:
            self.liste.addItem(i18n.tr('choix.creer_nouveau'))
        self.liste.setMouseTracking(True)
        self.liste.itemEntered.connect(self._sur_survol)
        self.liste.currentRowChanged.connect(self._eclairer)
        self.liste.itemDoubleClicked.connect(lambda _i: self.accept())
        disposition.addWidget(self.liste)

        boite = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self)
        boite.accepted.connect(self.accept)
        boite.rejected.connect(self.reject)
        disposition.addWidget(boite)

        self.liste.setCurrentRow(0)

    # -- surbrillance -------------------------------------------------------

    def _sur_survol(self, item):
        self._eclairer(self.liste.row(item))

    def _eclairer(self, rang):
        """Allume le sertissage du rang donné, ou éteint tout.

        C'est l'**esquisse** qui est montrée, jamais la révolution : une
        fonction PartDesign porte le solide CUMULÉ jusqu'à elle, si bien que
        le premier sertissage d'un corps en éclaire presque la totalité et
        que deux sertissages deviennent indiscernables (mesuré le
        15/09/2026). L'esquisse est un contour fermé posé exactement à
        l'endroit du sertissage.

        Ne lève jamais, et ne crée aucun objet : la seule chose modifiée est
        une visibilité, relevée avant d'être changée.
        """
        self._eteindre()
        if not (0 <= rang < len(self.candidats)):
            return
        esquisse = self._esquisses[rang]
        cible = esquisse if esquisse is not None else self.candidats[rang]
        try:
            if esquisse is not None:
                self._visibilite_avant[esquisse.Name] = (
                    esquisse, bool(esquisse.Visibility))
                esquisse.Visibility = True
            Gui.Selection.addSelection(cible)
            Gui.updateGui()
        except Exception as erreur:
            App.Console.PrintLog('[Swaging] surbrillance impossible : %s\n'
                                 % erreur)

    def _eteindre(self):
        """Rend les visibilités relevées et vide la sélection."""
        for esquisse, avant in list(self._visibilite_avant.values()):
            try:
                esquisse.Visibility = avant
            except Exception as erreur:
                App.Console.PrintLog('[Swaging] visibilité de %s : %s\n'
                                     % (getattr(esquisse, 'Name', '?'),
                                        erreur))
        self._visibilite_avant.clear()
        try:
            Gui.Selection.clearSelection()
        except Exception:
            pass

    # -- résultat -----------------------------------------------------------

    def choix(self):
        """L'objet retenu, `_CREER`, ou None si l'utilisateur a renoncé."""
        if self.result() != _ACCEPTE:
            return None
        rang = self.liste.currentRow()
        if 0 <= rang < len(self.candidats):
            return self.candidats[rang]
        # Hors de la liste des sertissages : c'est la ligne de création, qui
        # n'existe que si elle a été proposée. Sinon, rien n'est choisi.
        return _CREER if self.creation_possible else None

    def accept(self):
        self._eteindre()
        super(_DialogueChoixSertissage, self).accept()

    def reject(self):
        self._eteindre()
        super(_DialogueChoixSertissage, self).reject()


class _DialogueChoixPilotage(QtWidgets.QDialog):
    """Liste des paramètres nommés qui pourraient piloter le rayon.

    Volontairement PLUS SIMPLE que `_DialogueChoixSertissage` : pas de
    surbrillance 3D. Les candidats sont des cotes et des propriétés, pas des
    formes — il n'y a rien à allumer, et éclairer l'esquisse entière
    désignerait bien plus que la cote concernée.

    **Aucune issue de cette boîte n'annule le sertissage** : ni « ne pas
    lier », ni Échap, ni la croix. La question est accessoire, elle se pose
    en passant. C'est la leçon du 20/09/2026 sur StandardPartSelector, où
    une question posée devant le geste principal le bloquait — un refus y
    faisait sortir `main()` par son `return`.

    Les lignes viennent de `profil.lignes_pilotage()`, qui est pure et
    éprouvée hors FreeCAD : ce module ne fait que les traduire et les
    afficher.
    """

    def __init__(self, lignes, parent=None):
        super(_DialogueChoixPilotage, self).__init__(
            parent or Gui.getMainWindow())
        self.lignes = list(lignes)
        self.setWindowTitle(i18n.tr('app.titre'))
        self.setMinimumWidth(560)

        disposition = QtWidgets.QVBoxLayout(self)
        etiquette = QtWidgets.QLabel(i18n.tr('dlg.pilotage_texte'))
        etiquette.setWordWrap(True)
        disposition.addWidget(etiquette)

        aide = QtWidgets.QLabel('<i>%s</i>' % i18n.tr('dlg.pilotage_aide'))
        aide.setWordWrap(True)
        aide.setStyleSheet('color: #888;')
        disposition.addWidget(aide)

        self.liste = QtWidgets.QListWidget(self)
        for ligne in self.lignes:
            self.liste.addItem(_texte_ligne_pilotage(ligne))
        self.liste.itemDoubleClicked.connect(lambda _i: self.accept())
        disposition.addWidget(self.liste)

        boite = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self)
        boite.accepted.connect(self.accept)
        boite.rejected.connect(self.reject)
        disposition.addWidget(boite)

        self.liste.setCurrentRow(0)

    def choix(self):
        """Candidat retenu, ou None — refus, Échap, croix, tout vaut None."""
        if self.result() != _ACCEPTE:
            return None
        rang = self.liste.currentRow()
        if not (0 <= rang < len(self.lignes)):
            return None
        return self.lignes[rang]['candidat']


def _texte_ligne_pilotage(ligne):
    """Traduit une ligne rendue par `profil.lignes_pilotage()`."""
    args = dict(ligne.get('args') or {})
    if not args:
        return i18n.tr(ligne['cle'])
    cote = i18n.tr(args['cote_cle']).format(valeur=args['valeur'])
    motif = i18n.tr(args['motif_cle']).format(**(args['motif_args'] or {}))
    return i18n.tr(ligne['cle']).format(chemin=args['chemin'], cote=cote,
                                        motif=motif)


def _choisir_pilotage(candidats):
    """Demande si le rayon doit suivre un paramètre. Rend le candidat ou None.

    Ne pose RIEN s'il n'y a aucun candidat : une question sans réponse
    possible ne se pose pas.
    """
    lignes = profil.lignes_pilotage(candidats)
    if not lignes:
        return None
    dialogue = _DialogueChoixPilotage(lignes)
    _afficher_non_modal(dialogue)
    return dialogue.choix()


def _choisir_sertissage(candidats, action, creation_possible=True):
    """Demande lequel modifier, ou s'il faut créer. Rend l'objet, ou None.

    Trois situations mènent ici, et le texte les distingue :
    - `AMBIGU` : l'élément cliqué est une arête circulaire issue d'un
      sertissage — appui légitime d'un nouveau sertissage autant que morceau
      de l'existant ;
    - `CHOISIR` : l'élément cliqué vient de plusieurs sertissages ;
    - `DEMANDER` : le document n'a pas de nommage topologique, donc rien ne
      dit si l'élément cliqué appartient à un sertissage. Deviner serait une
      faute ; la question est posée.

    Rend `_CREER` si l'utilisateur veut un nouveau sertissage, `None` s'il
    renonce.
    """
    if action == profil.ACTION_AMBIGU:
        cle = 'dlg.choix_arete'
    elif action == profil.ACTION_CHOISIR:
        cle = ('dlg.choix_plusieurs' if creation_possible
               else 'dlg.choix_plusieurs_face')
    else:
        cle = ('dlg.choix_sans_histoire' if creation_possible
               else 'dlg.choix_sans_histoire_face')
    dialogue = _DialogueChoixSertissage(candidats, i18n.tr(cle),
                                        creation_possible)
    _afficher_non_modal(dialogue)
    return dialogue.choix()


def _sertissage_designe(element):
    """Le sertissage que la sélection désigne, ou `_CREER`, ou None.

    `element` est le relevé de sélection fait par l'appelant **avant** toute
    boîte de dialogue : le dialogue de choix éclaire les objets dans la vue,
    donc il écrase la sélection.
    """
    if element is None:
        return _CREER
    histoire = geometrie.histoire_element(element['objet'],
                                          element['nom_element'])
    action, candidats = profil.resolution_selection(
        histoire, element['body'], element.get('arete_possible', False))
    if action == profil.ACTION_CREER:
        return _CREER
    if action == profil.ACTION_MODIFIER:
        return candidats[0]
    return _choisir_sertissage(candidats, action,
                               element.get('arete_possible', False))


def _modifier(revolution, vue=None):
    """Rouvre un sertissage existant pour en changer les paramètres.

    Aucun objet n'est créé : la transaction ne sert qu'à rendre l'annulation
    exacte, et à offrir un seul Ctrl+Z à l'utilisateur.
    """
    varset = profil.varset_du_sertissage(revolution)
    sketch = profil.esquisse_du_sertissage(revolution)
    body = geometrie.resoudre_body_depuis_objet(revolution)
    if varset is None or sketch is None or body is None:
        _message(i18n.tr('app.titre'), i18n.tr('msg.modif_incomplete'),
                 erreur=True)
        return None

    document = body.Document
    if geometrie.document_partiel(document):
        _message(i18n.tr('app.titre'),
                 i18n.tr('msg.document_partiel_refus',
                         document=document.Label), erreur=True)
        return None
    data = profil.charger()
    arete = geometrie.arete_du_sketch(sketch)
    if arete is None:
        # Attachement illisible : les paramètres restent modifiables, seul
        # l'affichage de l'arête est dégradé. Refuser ici priverait
        # l'utilisateur d'une action qui, elle, fonctionne.
        arete = {'nom_edge': i18n.tr('info.indisponible'),
                 'rayon': profil.valeurs_courantes(varset, data).get(
                     profil.nom_parametre_rayon(data), 0.0),
                 'axe': None, 'objet': None, 'edge': None, 'centre': None}
    support = geometrie.support_attachement(body, arete.get('objet'))

    # Filet de sécurité de l'abandon : l'abandon de transaction suffit
    # normalement, mais un état relu vaut mieux qu'un état supposé — même
    # geste que `_defaire()` pour la création.
    valeurs_avant = profil.valeurs_courantes(varset, data)
    etat_avant = profil.etat_serti(varset, data)
    label_avant = varset.Label
    sens_avant = profil.sens_inverse(sketch)
    aspect.oublier_jalons(body)
    tip_avant = aspect.jalonner_tip(body, 'entrée')

    document.openTransaction(i18n.tr('app.titre'))
    # Mise à niveau d'un sertissage antérieur à l'état serti / non
    # serti. DANS la transaction : annuler doit la défaire aussi.
    rapport_etat = profil.mettre_a_niveau_etat(varset, sketch, data)
    if rapport_etat['proprietes'] or rapport_etat['expressions']:
        App.Console.PrintMessage(
            '[Swaging] %s\n'
            % i18n.tr('msg.mise_a_niveau_etat', varset=varset.Label,
                      proprietes=', '.join(rapport_etat['proprietes'])
                      or '-',
                      expressions=', '.join(rapport_etat['expressions'])
                      or '-'))
        document.recompute()
    for _chemin, _expression in rapport_etat['refus']:
        App.Console.PrintWarning(
            '[Swaging] %s\n' % i18n.tr('msg.expression_non_reconnue',
                                      chemin=_chemin,
                                      expression=_expression))
    dialogue = DialogueSwaging(arete, body, support, data, varset, sketch,
                               revolution, modification=True, vue=vue)
    accepte = _afficher_non_modal(dialogue) == _ACCEPTE
    aspect.jalonner_tip(body, 'sortie du dialogue')
    temoin = dialogue.nom_temoin()
    document_temoin = dialogue.document_temoin()

    if not accepte:
        try:
            document.abortTransaction()
        except Exception as erreur:
            App.Console.PrintWarning('[Swaging] abandon de transaction : '
                                     '%s\n' % erreur)
        # L'abandon peut RESSUSCITER le solide d'aperçu : sa suppression
        # faisait partie de la transaction annulée.
        if temoin and document_temoin.getObject(temoin) is not None:
            try:
                document_temoin.removeObject(temoin)
            except Exception as erreur:
                App.Console.PrintWarning('[Swaging] suppression de %s : '
                                         '%s\n' % (temoin, erreur))
        # L'abandon défait normalement jusqu'à `addProperty` (mesuré le
        # 24/09/2026) ; ce filet est idempotent et ne coûte rien s'il
        # n'a plus rien à défaire.
        profil.defaire_mise_a_niveau(varset, sketch, rapport_etat)
        profil.appliquer_valeurs(varset, valeurs_avant)
        profil.appliquer_etat(varset, data, etat_avant)
        varset.Label = label_avant
        profil.regler_sens(sketch, sens_avant)
        aspect.jalonner_tip(body, 'après abandon')
        document.recompute()
        aspect.jalonner_tip(body, 'après recompute')
        # Après l'abandon, jamais avant : une visibilité rétablie dans la
        # transaction serait défaite avec elle.
        aspect.retablir_tip(body, tip_avant)
        App.Console.PrintMessage('[Swaging] %s\n' % i18n.tr('msg.annule'))
        return None

    document.recompute()
    aspect.jalonner_tip(body, 'après recompute')
    document.commitTransaction()
    aspect.jalonner_tip(body, 'après commit')
    aspect.retablir_tip(body, tip_avant)
    App.Console.PrintMessage(
        '[Swaging] %s\n' % i18n.tr('msg.modifie', revolution=revolution.Label,
                                   corps=body.Label, varset=varset.Label))
    return varset, sketch, revolution


def lancer():
    """Enchaînement complet : sélection, construction, réglage, conservation."""
    if App.ActiveDocument is None:
        _message(i18n.tr('app.titre'), i18n.tr('msg.pas_de_document'),
                 erreur=True)
        return None

    # DOCUMENTS CHARGÉS PARTIELLEMENT (26/09/2026).
    #
    # Avant TOUTE lecture de la sélection : `App.openDocument()` la
    # VIDE (régression payée sur ORing le 13/09). Elle est donc relevée
    # en CHAÎNES, la complétion faite, puis reposée si elle a été
    # perdue. Compléter ici plutôt qu'au moment d'écrire : le
    # sertissage est construit avant même l'ouverture du dialogue, il
    # n'existe pas d'instant plus tardif où le document serait encore
    # intact.
    _selection = geometrie.relever_selection()
    _partiels = geometrie.completer_documents_partiels(App.ActiveDocument)
    for _nom in _partiels['completes']:
        App.Console.PrintMessage(
            '[Swaging] %s\n' % i18n.tr('msg.document_complete',
                                      document=_nom))
    for _nom in _partiels['partiels_restants']:
        App.Console.PrintWarning(
            '[Swaging] %s\n' % i18n.tr('msg.document_reste_partiel',
                                      document=_nom))
    if geometrie.restituer_selection(_selection):
        App.Console.PrintLog('[Swaging] %s\n'
                             % i18n.tr('msg.selection_restituee'))

    # La sélection porte DEUX informations : d'où vient l'élément cliqué, et
    # quelle arête servirait d'appui à une création. Le dialogue de choix
    # éclaire les objets dans la vue 3D, donc il ÉCRASE la sélection : les
    # deux relevés se font ici, avant toute boîte de dialogue.
    #
    # Une arête DU sertissage et une arête POUR un sertissage sont deux
    # natures différentes ; c'est `_sertissage_designe()` qui tranche.
    element = geometrie.resoudre_element_selectionne()
    arete = geometrie.resoudre_arete_selectionnee()
    vue = geometrie.contexte_vue()

    designe = _sertissage_designe(element)
    if designe is None:
        return None
    if designe is not _CREER:
        return _modifier(designe, vue)

    if arete is None:
        arete = demander_arete()
    if arete is None:
        _message(i18n.tr('app.titre'), i18n.tr('sel.rien'))
        return None

    # La sélection a livré son information : la vider évite de laisser les
    # arêtes en surbrillance de sélection pendant toute la session.
    try:
        Gui.Selection.clearSelection()
    except Exception:
        pass

    body = geometrie.resoudre_body_depuis_objet(arete['objet'])
    if body is None:
        _message(i18n.tr('app.titre'), i18n.tr('msg.pas_de_corps'),
                 erreur=True)
        return None
    if arete['rayon'] <= 0.0:
        _message(i18n.tr('app.titre'), i18n.tr('msg.rayon_nul'), erreur=True)
        return None

    # ⚠ À partir d'ici, TOUT se passe dans le document de la PIÈCE, jamais
    # dans `App.ActiveDocument`. En assemblage lié ce sont deux documents
    # différents : `construire()` crée dans celui du corps, et une
    # transaction ouverte sur l'assemblage n'y défait rien.
    document = body.Document
    if geometrie.document_partiel(document):
        # Refuser plutôt qu'avertir : FreeCAD avertissait déjà, douze
        # fois, et la modification a été perdue quand même (13/09/2026).
        _message(i18n.tr('app.titre'),
                 i18n.tr('msg.document_partiel_refus',
                         document=document.Label), erreur=True)
        return None

    support = geometrie.support_attachement(body, arete['objet'])
    data = profil.charger()
    # Relevé AVANT toute création : c'est l'état auquel l'utilisateur
    # s'attend à retrouver son document, quelle que soit l'issue.
    aspect.oublier_jalons(body)
    tip_avant = aspect.jalonner_tip(body, 'entrée')

    # Le sertissage est construit AVANT d'ouvrir le dialogue, aux valeurs du
    # modèle de référence, pour que l'utilisateur règle sur un aperçu réel.
    # Toute la session tient dans une seule transaction — ouverte sur le
    # document de la pièce, seul endroit où quoi que ce soit est créé.
    valeurs_initiales = profil.valeurs_reference(data)
    valeurs_initiales[profil.nom_parametre_rayon(data)] = arete['rayon']

    # PILOTAGE DU RAYON PAR UN PARAMÈTRE NOMMÉ (21/09/2026).
    #
    # La recherche des candidats est une LECTURE : elle ne touche à rien et
    # tourne toujours, ne serait-ce que pour journaliser ce qu'elle trouve.
    # La LIAISON est ensuite proposée, jamais imposée — l'utilisateur a
    # demandé que cela reste optionnel.
    #
    # Le lot 1 avait armé cette liaison par une variable d'environnement,
    # `SWAGING_PILOTAGE_AUTO`, le temps d'éprouver le mécanisme sans
    # interface. La boîte de choix l'a remplacée : le dispositif d'essai est
    # retiré avec ce qu'il servait à essayer.
    _expression_rayon = None
    _hors_corps = []
    try:
        _inventaire = geometrie.inventaire_parametres(
            document, profil.nom_varset())
        _sources = geometrie.esquisses_source(arete['objet'],
                                              arete['nom_edge'])
        # Le périmètre : le corps du sertissage, ses parents, la
        # racine. Calculé une fois, appliqué par `candidats_pilotage`.
        _portee = geometrie.portee_corps(document, body)
        _candidats = profil.candidats_pilotage(
            _inventaire, arete['rayon'], _sources,
            conteneurs_admis=_portee)
        # Ce que le périmètre a retiré. La même fonction PURE sans
        # périmètre : aucune règle n'est réécrite ici, et l'écart
        # entre les deux listes EST la mesure du filtre.
        _retenus = set(_c['chemin'] for _c in _candidats)
        _hors_corps = [_c for _c
                       in profil.candidats_pilotage(
                           _inventaire, arete['rayon'], _sources)
                       if _c['chemin'] not in _retenus]
    except Exception as _err_pilotage:
        _candidats = []
        App.Console.PrintWarning(
            '[Swaging] recherche de paramètres nommés impossible : %s\n'
            % _err_pilotage)
    if _hors_corps:
        App.Console.PrintMessage(
            '[Swaging] %s\n'
            % i18n.tr('msg.pilotage_hors_corps',
                      nombre=len(_hors_corps)))
        for _c in _hors_corps:
            App.Console.PrintMessage(
                '[Swaging]    %s  (%s)\n'
                % (_c['chemin'],
                   _c.get('conteneur_label') or _c.get('conteneur')
                   or '?'))
    if _candidats:
        App.Console.PrintMessage(
            '[Swaging] %s\n' % i18n.tr('msg.pilotage_candidats',
                                       nombre=len(_candidats)))
        for _c in _candidats:
            _certitude = i18n.tr('pilotage.genealogique') \
                if _c['genealogique'] else i18n.tr('pilotage.meme_valeur')
            # Un relais se nomme : sans cela, la ligne dirait « pilote cette
            # arête » d'un paramètre qui ne fait que relayer sa propre
            # source, présente dans la même liste (mesuré le 21/09).
            if _c.get('deja_pilote'):
                _certitude += ', ' + i18n.tr('pilotage.relais',
                                             source=_c['deja_pilote'])
            # Le conteneur est journalisé : c'est ce qui rend le
            # périmètre OBSERVABLE. Sans lui, un filtre qui ne
            # filtrerait rien passerait inaperçu.
            App.Console.PrintMessage(
                '[Swaging]    %s = %s  (%s, %s) [%s]\n'
                % (_c['chemin'], _c['valeur'], _c['role'], _certitude,
                   _c.get('conteneur_label') or _c.get('conteneur')
                   or 'racine'))
        # LA QUESTION. Elle remplace le point d'essai du lot 1.
        #
        # Aucune de ses issues n'annule le sertissage : « ne pas lier »,
        # Échap et la croix rendent None, et la suite se déroule comme si
        # aucun candidat n'avait été trouvé. Il n'y a donc, volontairement,
        # AUCUN `return` entre ici et l'ouverture de la transaction.
        _choix = _choisir_pilotage(_candidats)
        if _choix is not None:
            _expression_rayon = _choix['expression']
    else:
        App.Console.PrintLog('[Swaging] %s\n' % i18n.tr('msg.pilotage_aucun'))

    document.openTransaction(i18n.tr('app.titre'))
    try:
        varset, sketch, revolution, aspect_corps = profil.construire(
            body=body,
            support=support,
            nom_edge=arete['nom_edge'],
            rayon_arete=arete['rayon'],
            valeurs=valeurs_initiales,
            inverser=False,
            label_varset=geometrie.label_disponible(
                document, data['varset']['label']),
            data=data,
            expression_rayon=_expression_rayon)
    except Exception as erreur:
        document.abortTransaction()
        App.Console.PrintError('[Swaging] %s\n' % erreur)
        _message(i18n.tr('app.titre'), i18n.tr('msg.erreur', erreur=erreur),
                 erreur=True)
        return None

    noms = [revolution.Name, sketch.Name, varset.Name]
    dialogue = DialogueSwaging(arete, body, support, data,
                               varset, sketch, revolution, vue=vue)
    accepte = _afficher_non_modal(dialogue) == _ACCEPTE
    aspect.jalonner_tip(body, 'sortie du dialogue')
    # Le solide d'aperçu est normalement déjà retiré par le dialogue ; son
    # nom est ajouté au nettoyage par précaution, il n'a rien à faire dans le
    # document de l'utilisateur. Il ne vit dans le document du corps que si
    # celui-ci est aussi celui qu'on regarde.
    temoin = dialogue.nom_temoin()
    document_temoin = dialogue.document_temoin()
    if temoin and document_temoin is document:
        noms.insert(0, temoin)
    if not accepte:
        _defaire(document, noms)
        if temoin and document_temoin is not document:
            _retirer(document_temoin, temoin)
        # Après `_defaire`, donc après l'abandon de transaction : défaire
        # l'ajout d'une fonction PartDesign remet le Tip précédent, et rien
        # ne garantit qu'il soit réaffiché.
        aspect.jalonner_tip(body, 'après _defaire')
        aspect.retablir_tip(body, tip_avant)
        App.Console.PrintMessage('[Swaging] %s\n' % i18n.tr('msg.annule'))
        return None

    # Dernière remise de l'apparence du corps : entre la création et ici, des
    # dizaines de recalculs ont eu lieu pour l'aperçu, et le passage par le
    # mode « opération seule » a joué sur les visibilités.
    aspect.appliquer(revolution, aspect_corps)
    document.recompute()
    aspect.jalonner_tip(body, 'après recompute')
    document.commitTransaction()
    aspect.jalonner_tip(body, 'après commit')
    # Le Tip a changé — c'est la révolution neuve. L'invariant porte sur le
    # Tip COURANT, pas sur celui relevé à l'entrée.
    aspect.retablir_tip(body, tip_avant)

    if profil.est_entierement_contrainte(sketch) is False:
        App.Console.PrintWarning('[Swaging] %s\n'
                                 % i18n.tr('msg.non_resolue'))
        _message(i18n.tr('app.titre'), i18n.tr('msg.non_resolue'))
    redondantes = profil.diagnostic_solveur(sketch)
    if redondantes:
        texte = i18n.tr('msg.redondance', nombre=len(redondantes),
                        indices=', '.join(str(i + 1) for i in redondantes))
        App.Console.PrintWarning('[Swaging] %s\n' % texte)
        _message(i18n.tr('app.titre'), texte)
    App.Console.PrintMessage('[Swaging] %s\n'
                             % i18n.tr('msg.ok',
                                       revolution=revolution.Label,
                                       corps=body.Label,
                                       varset=varset.Label))
    try:
        Gui.Selection.clearSelection()
        Gui.Selection.addSelection(varset.Document.Name, varset.Name)
    except Exception:
        pass
    return varset, sketch, revolution
