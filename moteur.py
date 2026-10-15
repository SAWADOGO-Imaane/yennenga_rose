"""
Moteur de conversation, indépendant de l'interface.

Telegram (bot_telegram.py) et la démo web (demo_web.py) utilisent le même moteur :
    reponses = moteur.traiter(etat, message, vocal_langue=None)

- `etat` est un dict propre à chaque utilisatrice (créé vide au départ).
- `vocal_langue` vaut "fr", "mos" ou "dyu" si le message vient d'un vocal transcrit.
- Le moteur renvoie une liste de `Reponse` que l'interface affiche dans l'ordre.
"""
from dataclasses import dataclass, field
from datetime import date
import re

from questionnaire import QUESTIONS, lire_oui_non, resultat
from textes import LANGUES, texte

CLAVIER_LANGUE = ["1 Mooré", "2 Dioula", "3 Français"]
CLAVIER_MENU = ["1 🖐️", "2 🩺", "3 ⚠️", "4 📍", "5 ❓", "6 🔔", "7 🌐"]
CLAVIER_OUI_NON = ["1 ✅ Oui", "2 ❌ Non", "0 Menu"]
CLAVIER_RETOUR = ["0 Menu"]

CODES_LANGUE = {1: "mos", 2: "dyu", 3: "fr"}

# Chiffres dits à voix haute (pour les vocaux transcrits).
# Mooré et dioula : à vérifier avec les locutrices de l'équipe.
NOMBRES_PARLES = {
    "zéro": 0, "zero": 0,
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
    "yembre": 1, "yiibu": 2, "tãabo": 3, "taabo": 3, "naase": 4, "nu": 5, "yoobe": 6, "yopoe": 7,
    "kelen": 1, "fila": 2, "saba": 3, "naani": 4, "duuru": 5, "wɔɔrɔ": 6, "woro": 6, "wolonwula": 7,
}

MOTS_MENU = {"0", "menu", "/menu", "retour", "accueil"}


@dataclass
class Reponse:
    texte: str
    cle: str | None = None          # clé du message -> audio audios/<langue>/<cle>.*
    clavier: list[str] | None = None
    action: str | None = None       # "rappel_on" / "rappel_off"
    lire_a_voix_haute: bool = False  # réponse libre en français -> synthèse vocale possible


def lire_choix(message: str):
    """Extrait un numéro de choix ('1', '1 Mooré', 'deux', 'yiibu'...)."""
    t = message.strip().lower()
    m = re.match(r"^\s*(\d+)", t)
    if m:
        return int(m.group(1))
    mots = re.findall(r"[\wɔɛʋɩẽ']+", t)
    if len(mots) > 3:  # une phrase longue est une question, pas un choix
        return None
    for mot in mots:
        if mot in NOMBRES_PARLES:
            return NOMBRES_PARLES[mot]
    return None


class Moteur:
    def __init__(self, rag, centres):
        self.rag = rag
        self.centres = centres

    # ---------- utilitaires ----------
    def _msg(self, etat, cle, clavier=None, action=None):
        return Reponse(texte(cle, etat.get("langue", "fr")), cle=cle, clavier=clavier, action=action)

    def _menu(self, etat, avec_message=True):
        etat["mode"] = "menu"
        if avec_message:
            return [self._msg(etat, "menu", CLAVIER_MENU)]
        return []

    def _question(self, etat):
        i = etat["q_index"]
        q = QUESTIONS[i]
        r = self._msg(etat, f"q_{q['id']}", CLAVIER_OUI_NON)
        r.texte = f"({i + 1}/{len(QUESTIONS)}) {r.texte}"
        return r

    # ---------- point d'entrée ----------
    def traiter(self, etat: dict, message: str, vocal_langue: str | None = None) -> list[Reponse]:
        message = (message or "").strip()
        bas = message.lower()

        if bas in ("/start", "start") or "mode" not in etat:
            etat.clear()
            etat["mode"] = "langue"
            return [Reponse(texte("choix_langue"), cle="choix_langue", clavier=CLAVIER_LANGUE)]

        mode = etat["mode"]

        if mode != "langue" and (bas in MOTS_MENU or lire_choix(message) == 0):
            return self._menu(etat)

        if mode == "langue":
            return self._choisir_langue(etat, message)
        if mode == "menu":
            return self._traiter_menu(etat, message, vocal_langue)
        if mode == "questionnaire":
            return self._traiter_questionnaire(etat, message)
        if mode == "ville":
            return self._traiter_ville(etat, message)
        if mode == "question":
            return self._traiter_question(etat, message, vocal_langue)
        return self._menu(etat)

    # ---------- étapes ----------
    def _choisir_langue(self, etat, message):
        choix = lire_choix(message)
        bas = message.lower()
        if choix not in CODES_LANGUE:
            # On accepte aussi le nom de la langue
            for code, nom in LANGUES.items():
                if nom.lower()[:4] in bas:
                    choix = [k for k, v in CODES_LANGUE.items() if v == code][0]
        if choix not in CODES_LANGUE:
            return [Reponse(texte("choix_langue"), cle="choix_langue", clavier=CLAVIER_LANGUE)]
        etat["langue"] = CODES_LANGUE[choix]
        return [self._msg(etat, "bienvenue")] + self._menu(etat)

    def _traiter_menu(self, etat, message, vocal_langue):
        choix = lire_choix(message)

        if choix is None:
            # Un vocal en français qui n'est pas un chiffre = une question libre
            if vocal_langue == "fr" and len(message.split()) >= 3:
                return self._traiter_question(etat, message, vocal_langue)
            if vocal_langue in ("mos", "dyu"):
                return [self._msg(etat, "vocal_langue_locale")] + self._menu(etat)
            # Un texte écrit long = une question libre
            if len(message.split()) >= 4:
                return self._traiter_question(etat, message, vocal_langue)
            return [self._msg(etat, "choix_invalide")] + self._menu(etat)

        if choix == 1:
            return [self._msg(etat, "autopalpation", CLAVIER_MENU)]
        if choix == 2:
            etat.update(mode="questionnaire", q_index=0, reponses={})
            return [self._msg(etat, "questionnaire_intro"), self._question(etat)]
        if choix == 3:
            return [self._msg(etat, "signes_alerte", CLAVIER_MENU)]
        if choix == 4:
            return self._demander_ville(etat)
        if choix == 5:
            etat["mode"] = "question"
            return [self._msg(etat, "question_intro", CLAVIER_RETOUR)]
        if choix == 6:
            if etat.get("rappel"):
                etat["rappel"] = False
                return [self._msg(etat, "rappel_desactive", CLAVIER_MENU, action="rappel_off")]
            etat["rappel"] = True
            return [self._msg(etat, "rappel_active", CLAVIER_MENU, action="rappel_on")]
        if choix == 7:
            etat["mode"] = "langue"
            return [Reponse(texte("choix_langue"), cle="choix_langue", clavier=CLAVIER_LANGUE)]
        return [self._msg(etat, "choix_invalide")] + self._menu(etat)

    def _traiter_questionnaire(self, etat, message):
        rep = lire_oui_non(message)
        if rep is None:
            return [self._msg(etat, "reponse_oui_non"), self._question(etat)]

        etat["reponses"][QUESTIONS[etat["q_index"]]["id"]] = rep
        etat["q_index"] += 1
        if etat["q_index"] < len(QUESTIONS):
            return [self._question(etat)]

        issue = resultat(etat["reponses"])
        reponses = [self._msg(etat, f"resultat_{issue}")]
        if issue == "consulter":
            return reponses + self._demander_ville(etat)
        return reponses + self._menu(etat)

    def _demander_ville(self, etat):
        etat["mode"] = "ville"
        r = self._msg(etat, "demande_ville", self.centres.options())
        r.texte += "\n" + "\n".join(self.centres.options())
        return [r]

    def _traiter_ville(self, etat, message):
        choix = lire_choix(message)
        ville = self.centres.par_choix(choix) if choix else self.centres.par_nom(message)
        if ville is None and choix is None and len(message) < 3:
            return self._demander_ville(etat)

        if ville is None:
            reponses = [self._msg(etat, "centres_autre")]
        else:
            reponses = [
                self._msg(etat, "centres_intro"),
                Reponse(self.centres.formater(ville)),
                self._msg(etat, "centres_autre"),
            ]
        if date.today().month == 10:
            reponses.append(self._msg(etat, "info_octobre"))
        return reponses + self._menu(etat)

    def _traiter_question(self, etat, message, vocal_langue):
        etat["mode"] = "question"
        if vocal_langue in ("mos", "dyu"):
            return [self._msg(etat, "vocal_langue_locale")] + self._menu(etat)
        reponse = self.rag.repondre(message)
        return [
            Reponse(reponse, lire_a_voix_haute=True),
            self._msg(etat, "question_suite", CLAVIER_RETOUR),
        ]
