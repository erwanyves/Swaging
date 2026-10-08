# -*- coding: utf-8 -*-
"""Catalogue des chaînes d'interface de la macro Swaging.

Un seul catalogue (français) pour cette version. Toutes les chaînes visibles
par l'utilisateur passent par `tr()` et vivent ici : ajouter une langue
consiste à ajouter un dictionnaire dans `_CATALOGUES` et à changer `_LANGUE`,
sans toucher au reste du code.
"""

_LANGUE = 'fr'

_FR = {
    # --- Titres et cadres ---------------------------------------------------
    'app.titre': 'Swaging',
    'dlg.titre': 'Swaging — sertissage sur arête circulaire',
    'dlg.groupe_arete': 'Arête de référence',
    'dlg.groupe_params': 'Paramètres du sertissage (VarSet)',
    'dlg.groupe_options': 'Options',

    # --- Sélection 3D -------------------------------------------------------
    'sel.titre': 'Sélection de l\'arête',
    'sel.instruction': ('Cliquez une arête circulaire dans la vue 3D.\n'
                        'Elle définira l\'axe d\'insertion (Z) et le rayon '
                        'intérieur du sertissage.'),
    'sel.annuler': 'Annuler',
    'sel.rien': ('Aucune arête circulaire sélectionnée.\n\n'
                 'Sélectionnez une arête circulaire (cercle ou arc de cercle) '
                 'puis relancez la macro.'),

    # --- Informations sur l'arête ------------------------------------------
    'info.corps': 'Corps :',
    'info.support': 'Support d\'attachement :',
    'info.arete': 'Arête :',
    'info.rayon': 'Rayon détecté :',
    'info.axe': 'Axe d\'insertion (Z) :',

    # --- Champs -------------------------------------------------------------
    'champ.nom_varset': 'Nom du VarSet :',
    'champ.inverser': 'Inverser le sens d\'insertion (Z)',
    'champ.inverser_aide': ('Retourne le sertissage de l\'autre côté du plan '
                            'de l\'arête. Le sens radial est inchangé.'),
    'champ.etat': 'Représentation :',
    'champ.serti': 'Sertie',
    'champ.serti_aide': (
        'La lèvre est rabattue à l\'angle de sertissage : la pièce '
        'telle qu\'elle est une fois montée.'),
    'champ.non_serti': 'Non sertie (avant sertissage)',
    'champ.non_serti_aide': (
        'La lèvre est droite : la pièce telle qu\'elle est usinée, '
        'avant montage. La longueur de lèvre est conservée ; l\'angle '
        'de sertissage, lui, reste saisi et reprend la main au retour.'),
    'champ.etat_indisponible': (
        'Ce sertissage ne porte pas le paramètre d\'état et n\'a pas pu '
        'être mis à niveau. Recréez-le pour disposer des deux '
        'représentations.'),
    'param.pilote': 'piloté par {source}',
    'param.pilote_aide': (
        'Ce paramètre est piloté par une expression : {source}.\n'
        'Il se modifie à sa source, pas ici.'),
    'champ.reinit': 'Valeurs du modèle de référence',
    'champ.apercu': 'Aperçu en direct dans la vue 3D',
    'champ.transparence': 'Montrer le sertissage seul, en transparence',
    'champ.transparence_aide': (
        'Affiche le corps tel qu\'il est avant sertissage, plus la matière '
        'ajoutée seule, en transparence. Rendre la fonction elle-même '
        'transparente rendrait tout le corps transparent : une révolution '
        'additive est fusionnée au corps.'),
    'champ.apercu_aide': (
        'Le sertissage est construit dès l\'ouverture et se met à jour à '
        'chaque changement de valeur. Décochez si le recalcul est trop lent '
        'sur une pièce lourde : les valeurs seront alors appliquées à la '
        'validation seulement.'),
    'champ.apercu_fige': (
        'Aperçu suspendu — les valeurs affichées ne sont pas encore '
        'appliquées au modèle.'),

    # --- Étiquettes des paramètres du VarSet -------------------------------
    # Les noms techniques sont anglais (nomenclature Swaging, écrite dans les
    # documents produits) ; les étiquettes d'interface restent françaises.
    'param.InnerRadius': 'Rayon intérieur',
    'param.SwagingRadius': 'Rayon de sertissage',
    'param.BaseThickness': 'Épaisseur de base',
    'param.HeadThickness': 'Épaisseur de tête',
    'param.AxialOffset': 'Offset axial',
    'param.LipLength': 'Longueur de lèvre',
    'param.SwagingAngle': 'Angle de sertissage',
    'param.UnswagedAngle': 'Angle « non sertie »',

    # --- Infobulles des paramètres -----------------------------------------
    'varset.doc.inner_radius': ('Rayon intérieur du sertissage, mesuré depuis '
                                'l\'axe d\'insertion. Initialisé au rayon de '
                                'l\'arête sélectionnée, puis librement '
                                'modifiable.'),
    'varset.doc.swaging_radius': ('Rayon de courbure de la lèvre, côté '
                                  'intérieur.'),
    'varset.doc.base_thickness': ('Épaisseur du sertissage à sa base, mesurée '
                                  'radialement.'),
    'varset.doc.head_thickness': ('Épaisseur du sertissage à son extrémité. '
                                  'Pilote aussi le chanfrein de tête '
                                  '(épaisseur / 3).'),
    'varset.doc.axial_offset': ('Hauteur du pied droit, entre le plan de '
                                'l\'arête et le début de la courbure.'),
    'varset.doc.lip_length': ('Longueur développée totale de la lèvre : '
                              'partie courbe + partie droite.'),
    'varset.doc.swaged': ('Vrai : la lèvre est rabattue à l\'angle de '
                          'sertissage. Faux : elle est droite, la pièce '
                          'est représentée avant sertissage. Ce paramètre '
                          'peut être piloté depuis un assemblage.'),
    'varset.doc.unswaged_angle': ('Angle donné à la lèvre dans la '
                                  'représentation NON sertie. Il ne peut '
                                  'pas être nul : à 0° exactement, la '
                                  'révolution dégénère silencieusement. '
                                  '0,1° est indiscernable d\'une lèvre '
                                  'droite (0,004 % de volume).'),
    'varset.doc.swaging_angle': ('Angle de la partie courbe de la lèvre. La '
                                 'partie droite est le complément de la '
                                 'longueur de lèvre.'),

    # --- Choix entre modifier et créer -------------------------------------
    'dlg.choix_arete': (
        'Cette arête circulaire appartient à un sertissage existant — mais '
        'c\'est aussi un appui valable pour un nouveau sertissage.\n\n'
        'Que voulez-vous faire ?'),
    'dlg.choix_plusieurs': (
        'L\'élément sélectionné provient de plusieurs sertissages.\n'
        'Lequel voulez-vous modifier ?'),
    'dlg.choix_plusieurs_face': (
        'Cette face provient de plusieurs sertissages.\n'
        'Lequel voulez-vous modifier ?'),
    'dlg.choix_sans_histoire_face': (
        'Ce document ne conserve pas l\'historique des éléments : impossible '
        'de savoir de quel sertissage vient cet élément.\n\n'
        'Lequel voulez-vous modifier ?'),
    'dlg.choix_sans_histoire': (
        'Ce document ne conserve pas l\'historique des éléments : impossible '
        'de savoir si l\'élément sélectionné appartient à un sertissage '
        'existant.\n\n'
        'Que voulez-vous faire ?'),
    'choix.creer_nouveau': 'Créer un nouveau sertissage sur cette arête',
    # ⚠ Le paramètre est un DIAMÈTRE, pas un rayon : jusqu'au
    # 21/09/2026 cette ligne annonçait « Ø intérieur » et imprimait
    # `InnerRadius`, qui est un rayon — 18,00 affiché pour un Ø de
    # 36,00 (signalé par l'utilisateur sur une capture). Classe A du
    # mémorandum : décrire ce que VOIT l'utilisateur.
    'choix.entree': '{nom} — Ø intérieur {diametre:.2f} mm   ({varset})',
    'choix.survol_aide': ('Survolez une ligne, ou déplacez-vous au clavier : '
                          'l\'esquisse du sertissage correspondant '
                          's\'éclaire dans la vue 3D.'),
    'info.indisponible': '(attachement illisible)',

    # --- Boutons ------------------------------------------------------------
    'btn.modifier': 'Modifier',
    'btn.creer': 'Conserver le sertissage',
    'btn.annuler': 'Annuler',

    # --- Marqueur d'identification -----------------------------------------
    'prop.swg_version': ('Version du schéma de sertissage. Sa présence '
                         'identifie cette opération comme un sertissage '
                         'créé par la macro Swaging.'),
    'prop.swg_varset': ('VarSet portant les paramètres de ce sertissage. '
                        'Ce lien reste valide où que le VarSet soit rangé.'),
    'prop.swg_corps': ('Ce corps contient au moins un sertissage. Sert à '
                       'SmartFinder pour proposer la macro ; l\'identité '
                       'de chaque sertissage est portée par l\'opération.'),

    # --- Messages -----------------------------------------------------------
    # --- Pilotage du rayon par un paramètre nommé (21/09/2026) ------
    # Le point d'essai SWAGING_PILOTAGE_AUTO a vécu du lot 1 au lot 2 :
    # la boîte de choix le remplace. Sa clé est retirée avec lui.
    'pilotage.genealogique': 'pilote cette arête',
    'pilotage.meme_valeur': 'même valeur',
    'pilotage.relais': 'relais vers {source}',
    'pilotage.autre_sertissage': "paramètre d'un autre sertissage",
    'choix.cote_rayon': 'R {valeur:.2f} mm',
    'choix.cote_diametre': 'Ø {valeur:.2f} mm',
    'choix.pilotage_ligne': '{chemin} — {cote} — {motif}',
    'choix.pilotage_ne_pas_lier': (
        'Ne pas lier — le rayon reste une valeur fixe'),
    'dlg.pilotage_texte': (
        "Le rayon de cette arête correspond à un paramètre nommé du "
        'document. Voulez-vous que le sertissage le suive ?'),
    'dlg.pilotage_aide': (
        "Aucun choix ici n'annule le sertissage : la création "
        'continue dans tous les cas.'),
    'msg.pilotage_pose': (
        'Rayon piloté : {parametre} = {expression}'),
    'msg.pilotage_refuse': (
        'Liaison refusée par FreeCAD ({expression}) : {erreur} — '
        'le rayon reste une valeur fixe.'),
    'msg.pilotage_ecriture_sautee': (
        '{parametre} est piloté par une expression : la valeur saisie '
        'n\'est pas écrite.'),
    'msg.pilotage_candidats': (
        '{nombre} paramètre(s) nommé(s) correspondent au rayon ou au '
        'diamètre de l\'arête.'),
    'msg.pilotage_hors_corps': (
        '{nombre} paramètre(s) de même valeur écarté(s) : ils vivent '
        'dans un autre corps.'),
    'msg.pilotage_aucun': (
        'Aucun paramètre nommé ne correspond : rayon fixe.'),

    'msg.pas_de_document': 'Aucun document actif.',
    'msg.pas_de_corps': ('L\'arête sélectionnée n\'appartient à aucun corps '
                         'PartDesign. Le sertissage est ajouté en tant que '
                         'fonction d\'un corps existant.'),
    'msg.rayon_nul': 'Le rayon intérieur du sertissage doit être positif.',
    'msg.longueur_levre_courte': (
        'La longueur de lèvre ({levre:.3f} mm) est inférieure à la longueur '
        'de la partie courbe ({arc:.3f} mm) : la partie droite serait '
        'négative et l\'esquisse ne pourrait pas se résoudre.'),
    'msg.profil_traverse_axe': (
        'La lèvre rentre de {rentree:.3f} mm vers l\'axe, pour un rayon '
        'intérieur de seulement {rayon:.3f} mm : le profil traverserait '
        'l\'axe de révolution.\n\n'
        'Augmentez le rayon intérieur, ou réduisez le rayon de sertissage, '
        'l\'angle ou la longueur de lèvre.'),
    'msg.echec_contrainte': ('Échec à la contrainte #{index} ({type}) : '
                             '{erreur}'),
    'msg.non_resolue': ('L\'esquisse n\'est pas entièrement contrainte après '
                        'construction, alors que le profil de référence '
                        'l\'est. Le sertissage a été créé, mais son esquisse '
                        'mérite une vérification.'),
    'msg.ok': ('Sertissage créé : {revolution} dans le corps {corps}. '
               'Paramètres modifiables dans {varset}.'),
    'msg.modifie': ('Sertissage modifié : {revolution} dans le corps '
                    '{corps}, paramètres dans {varset}.'),
    'msg.modif_incomplete': (
        'Ce sertissage est marqué, mais son VarSet, son esquisse ou son '
        'corps sont introuvables. Il a pu être partiellement supprimé. '
        'La modification est impossible ; la création reste disponible en '
        'désélectionnant tout.'),
    'msg.erreur': 'Erreur : {erreur}',
    'msg.echec_apercu': ('L\'aperçu n\'a pas pu être mis à jour : {erreur}\n\n'
                         'Les dernières valeurs valides restent en place.'),
    'msg.angle_non_serti_nul': (
        'L\'angle de la représentation non sertie doit être strictement '
        'positif : à 0° exactement, l\'esquisse se résout encore mais la '
        'révolution dégénère, sans aucun message.'),
    'msg.mise_a_niveau_etat': (
        'Sertissage {varset} complété pour la représentation sertie / '
        'non sertie — paramètres ajoutés : {proprietes} ; expressions '
        'reposées : {expressions}. Annuler défait aussi ce complètement.'),
    'msg.expression_non_reconnue': (
        'Expression {chemin} laissée telle quelle : « {expression} » '
        'n\'est pas une forme connue de cette macro. La représentation '
        'non sertie pourrait ne pas agir sur ce sertissage.'),
    'msg.document_complete': (
        'Document « {document} » complété : il était chargé '
        'partiellement, vos modifications y seront désormais '
        'enregistrées.'),
    'msg.document_reste_partiel': (
        'Document « {document} » toujours chargé PARTIELLEMENT : FreeCAD '
        'n\'y enregistrera rien et ne le recalculera pas. Ouvrez ce '
        'fichier directement (Fichier > Ouvrir), puis relancez la '
        'macro.'),
    'msg.document_partiel_refus': (
        'Le document « {document} » est chargé partiellement. FreeCAD '
        'n\'y enregistre aucune modification et refuse de le '
        'recalculer : la macro s\'arrête plutôt que d\'écrire dans le '
        'vide.\n\n'
        'Ouvrez ce fichier directement (Fichier > Ouvrir), puis '
        'relancez la macro.'),
    'msg.selection_restituee': (
        'Sélection reposée après complétion des documents partiels.'),
    'msg.annule': 'Sertissage annulé, document laissé dans son état initial.',
    'msg.contrainte_ref_ignoree': (
        'Cote de référence (longueur d\'arc) écartée : cette version de '
        'FreeCAD ne permet pas de la rendre non pilotante, et la garder '
        'pilotante rendrait l\'esquisse surcontrainte. Sans effet sur la '
        'géométrie — elle n\'était qu\'un affichage.'),
    'msg.redondance': (
        'FreeCAD signale {nombre} contrainte(s) redondante(s) ou en conflit '
        'dans l\'esquisse créée : {indices}. La géométrie est correcte mais '
        'l\'esquisse mérite un contrôle.'),
}

_CATALOGUES = {'fr': _FR}


def langue():
    """Code de la langue active."""
    return _LANGUE


def tr(cle, **kwargs):
    """Chaîne traduite pour `cle`, formatée avec `kwargs`.

    Une clé absente est renvoyée telle quelle plutôt que de lever : une
    chaîne manquante ne doit jamais empêcher la macro de fonctionner.
    """
    catalogue = _CATALOGUES.get(_LANGUE, _FR)
    texte = catalogue.get(cle, _FR.get(cle, cle))
    if kwargs:
        try:
            texte = texte.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return texte


def cles():
    """Liste triée des clés du catalogue de référence (contrôle de parité)."""
    return sorted(_FR.keys())
