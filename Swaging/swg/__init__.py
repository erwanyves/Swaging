# -*- coding: utf-8 -*-
"""Modules de la macro Swaging.

Nom de paquet volontairement namespacé (`swg`) plutôt que générique
(`modules`, `utils`, `i18n`...) : le cache `sys.modules` de Python est indexé
par nom et non par chemin, et un nom générique provoquerait un chargement
croisé avec les autres macros du dossier Macro selon l'ordre de lancement
dans une même session FreeCAD.
"""

__all__ = ['i18n', 'geometrie', 'aspect', 'profil', 'dialogue']
