"""
Questionnaire d'orientation (pas de diagnostic).

Règle :
- un seul OUI à une question "alerte"      -> CONSULTER rapidement
- sinon, un OUI à un facteur de risque     -> parler du DEPISTAGE
- sinon                                     -> SURVEILLANCE (auto-examen mensuel)

Sources : conférence des Drs OUEDRAOGO (gynécologie), ODC, 14 octobre 2026 :
l'âge est le 1er facteur de risque ; en Afrique le cancer apparaît plus jeune
et évolue plus vite (d'où le seuil de 35 ans) ; antécédents de maladie du sein
et antécédents familiaux sont des facteurs de risque.
⚠️ Liste et règles à faire valider par la médecin.
"""

QUESTIONS = [
    {"id": "boule", "alerte": True},
    {"id": "peau", "alerte": True},
    {"id": "ecoulement", "alerte": True},
    {"id": "mamelon", "alerte": True},
    {"id": "forme", "alerte": True},
    {"id": "plaie", "alerte": True},
    {"id": "douleur", "alerte": False},
    {"id": "famille", "alerte": False},
    {"id": "antecedent", "alerte": False},
    {"id": "age", "alerte": False},
]

# Mots acceptés pour OUI / NON (tapés ou transcrits d'un vocal).
# Mooré : "ẽẽ" / "ayo" ; Dioula : "ɔwɔ" / "ayi"  -> à vérifier avec les locutrices.
OUI = {"1", "oui", "o", "ouais", "ouii", "ouaip", "yes", "yep",
       "ẽẽ", "ee", "eeh", "ɔwɔ", "owo", "awo", "ɔɔ"}
NON = {"2", "non", "n", "nn", "no", "ayo", "ayi", "ayɩ"}


def lire_oui_non(texte: str):
    """Renvoie True (oui), False (non) ou None (pas compris)."""
    mots = texte.strip().lower().replace(",", " ").replace(".", " ").split()
    for mot in mots:
        if mot in OUI:
            return True
        if mot in NON:
            return False
    return None


def resultat(reponses: dict) -> str:
    """reponses = {"boule": True, "peau": False, ...}"""
    if any(reponses.get(q["id"]) for q in QUESTIONS if q["alerte"]):
        return "consulter"
    if any(reponses.get(q["id"]) for q in QUESTIONS if not q["alerte"]):
        return "depistage"
    return "surveillance"
