"""Tests du moteur :  python -m pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from centres import Centres  # noqa: E402
from moteur import Moteur, lire_choix  # noqa: E402
from questionnaire import QUESTIONS, lire_oui_non, resultat  # noqa: E402
from rag import RAG  # noqa: E402

moteur = Moteur(RAG(), Centres())


def demarrer(langue="3"):
    etat = {}
    moteur.traiter(etat, "/start")
    moteur.traiter(etat, langue)
    return etat


def test_choix_langue():
    etat = {}
    r = moteur.traiter(etat, "/start")
    assert r[0].cle == "choix_langue"
    r = moteur.traiter(etat, "1 Mooré")
    assert etat["langue"] == "mos" and etat["mode"] == "menu"
    assert r[-1].cle == "menu"


def test_lire_choix():
    assert lire_choix("2 🩺") == 2
    assert lire_choix("deux") == 2
    assert lire_choix("yiibu") == 2
    assert lire_choix("Est-ce qu'un homme peut avoir un cancer du sein ?") is None


def test_oui_non():
    assert lire_oui_non("1 ✅ Oui") is True
    assert lire_oui_non("2 ❌ Non") is False
    assert lire_oui_non("ayo") is False
    assert lire_oui_non("peut-être") is None


def test_un_seul_signe_alerte_suffit():
    assert resultat({"boule": True}) == "consulter"
    assert resultat({"famille": True, "age": True}) == "depistage"
    assert resultat({}) == "surveillance"


def test_questionnaire_complet_alerte_puis_centres():
    etat = demarrer()
    moteur.traiter(etat, "2")
    assert etat["mode"] == "questionnaire"
    moteur.traiter(etat, "1")  # boule = oui
    for _ in QUESTIONS[1:]:
        r = moteur.traiter(etat, "2")
    assert any(x.cle == "resultat_consulter" for x in r)
    assert etat["mode"] == "ville"
    r = moteur.traiter(etat, "1")  # Ouagadougou
    assert any("Yalgado" in x.texte for x in r)
    assert etat["mode"] == "menu"


def test_questionnaire_reponse_invalide():
    etat = demarrer()
    moteur.traiter(etat, "2")
    r = moteur.traiter(etat, "je ne sais pas")
    assert r[0].cle == "reponse_oui_non"
    assert etat["q_index"] == 0


def test_retour_menu_pendant_questionnaire():
    etat = demarrer()
    moteur.traiter(etat, "2")
    moteur.traiter(etat, "0 Menu")
    assert etat["mode"] == "menu"


def test_ville_par_nom_et_autre():
    etat = demarrer()
    moteur.traiter(etat, "4")
    r = moteur.traiter(etat, "bobo")
    assert any("Sourô Sanou" in x.texte for x in r)
    moteur.traiter(etat, "4")
    r = moteur.traiter(etat, "Gaoua")
    assert r[0].cle == "centres_autre"


def test_rappel_on_off():
    etat = demarrer()
    assert moteur.traiter(etat, "6")[0].action == "rappel_on"
    assert moteur.traiter(etat, "6")[0].action == "rappel_off"


def test_question_libre_rag():
    etat = demarrer()
    moteur.traiter(etat, "5")
    r = moteur.traiter(etat, "Est-ce que le cancer du sein est contagieux ?")
    assert "contagieux" in r[0].texte.lower()


def test_question_tapee_depuis_le_menu():
    etat = demarrer()
    r = moteur.traiter(etat, "Est-ce qu'un homme peut avoir un cancer du sein ?")
    assert "homme" in r[0].texte.lower()


def test_question_hors_sujet():
    etat = demarrer()
    moteur.traiter(etat, "5")
    r = moteur.traiter(etat, "Quel est le prix du ciment à Koupéla ?")
    assert "agent de santé" in r[0].texte


def test_vocal_moore_hors_menu():
    etat = demarrer("1")
    r = moteur.traiter(etat, "m data n bãng bãag ning", vocal_langue="mos")
    assert r[0].cle == "vocal_langue_locale"


def test_vocal_chiffre_parle():
    etat = demarrer("1")
    r = moteur.traiter(etat, "tãabo", vocal_langue="mos")
    assert r[0].cle == "signes_alerte"


def test_contraception_rag():
    etat = demarrer()
    moteur.traiter(etat, "5")
    r = moteur.traiter(etat, "Est-ce que la pilule donne le cancer du sein ?")
    assert "contraception" in r[0].texte.lower()


def test_octobre_gratuit(monkeypatch):
    import moteur as m
    class FausseDate:
        @staticmethod
        def today():
            import datetime
            return datetime.date(2026, 10, 15)
    monkeypatch.setattr(m, "date", FausseDate)
    etat = demarrer()
    moteur.traiter(etat, "4")
    r = moteur.traiter(etat, "1")
    assert any(x.cle == "info_octobre" for x in r)
