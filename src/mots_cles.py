"""Listes de mots-clés par cluster thématique.

Toutes les entrées doivent être en minuscules et sans accents (cf. utils.normaliser),
puisque le matching se fait sur du texte déjà normalisé de la même façon.
"""

MOTS_CLES_PRESTATIONS = [
    "amo", "maitrise d'ouvrage", "audit", "concours", "contenu",
    "conception", "realisation", "conseil assistance", "communication",
    "conseil communication", "etude", "ingenierie", "maintenance",
    "maitrise d'oeuvre", "maitrise d'œuvre", "prestations audiovisuelles",
]

MOTS_CLES_NUMERIQUE_MULTIMEDIA = [
    "application", "audiovisuel", "communication multimedia", "digital",
    "film", "immersif", "interaction", "internet",
    "interface", "intranet", "integration", "modelisation",
    "multimedia", "numerique", "numerisation", "site internet", 
    "virtuel", "web", "restauration numerique", "webdesign",
]

MOTS_CLES_MUSEO_SCENO = [
    "equipement museographique", "exposition", "expographie", "mediation",
    "museographie", "museographique", "scenographie", "scenographique",
    "ingenierie scenique", "mediation culturelle", "programmation", "visite",
]

MOTS_CLES_SECTEURS_TRANSVERSES = [
    "archive", "culture", "danse", "ecologie", "gastronomie", "luxe",
    "monument", "musique", "oeuvre d'art", "œuvre d'art", "opera ",
    "patrimoine", "patrimonial", "signaletique", "theatre", "universite",
]

MOTS_CLES_INSTITUTIONS = [
    'arte france', 'beaux arts', 'beaux-arts', 'bnf', 'cap digital',
    'carre plantagenet', 'centquatre', 'centre national des arts plastiques', "cnap",
    'centre national du cinema', "cnc", 'centre pompidou', "crt", 'chateau',
    'chateau de fontainebleau', 'chateau de versailles', 'cinematheque',
    "cite de l'architecture et du patrimoine", "cite de l'economie",
    'cite de la ceramique', 'cite de la musique', 'cmn',
    'comite regional du tourisme', 'fondation le corbusier', 'grand palais',
    'grande bibliotheque', 'inrap', 'institut du monde arabe', "flc", 
    'institut francais', 'institut national audiovisuel',
    'intelligence des patrimoines', 'les abattoirs', 'arts decoratifs',
    'les champs libres', 'louvre lens', 'mac val', 'mac/val',
    'mairie de paris', "maison de l'histoire de france", 'monnaie de paris',
    'monuments historiques', 'monuments nationaux', 'mucem',
    'musee', 'museum', "mnam", "mnhn", "mnaag", 'guimet', 'palais de tokyo',
    'palais', 'palais tokyo', 'paris musees', 'petit palais', 'philharmonie de paris', 'quai branly', "mqb",
    'radio france', 'reunion des musees nationaux', 'rmn', "rmn-gp", 'solideo', 'universcience',
]
