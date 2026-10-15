"""
Fabrique À L'AVANCE la voix française :
- de tous les messages fixes du bot (menu, signes d'alerte, questions...) -> audios/fr/<clé>.ogg
- de tous les passages de la base de connaissances (data/docs) -> audios/fr/docs/<empreinte>.ogg
  (utilisés quand une femme pose une question en VOCAL)

Pendant la démo, le bot envoie ces fichiers tout prêts : la réponse vocale
est instantanée, même avec une connexion lente.

    python generer_voix_fr.py            -> crée les voix manquantes
    python generer_voix_fr.py --refaire  -> recrée toutes les voix (après modification de textes.py)

À relancer chaque fois que tu modifies un texte dans textes.py.
"""
import sys
import time

import config
from audio import reponse_vocale_fr
from rag import RAG, cle_passage, nettoyer_markdown
from textes import TEXTES

# Ce que WhatsApp affiche en plus sous certains messages (cf. texte_whatsapp)
SUFFIXE_OUI_NON = "\n\n1 = Oui   ·   2 = Non   ·   0 = Menu"
CLES_OUI_NON = {c for c in TEXTES if c.startswith("q_")}
CLES_RETOUR = {"question_intro", "question_suite"}


def texte_a_lire(cle: str) -> str:
    texte = TEXTES[cle]
    if cle in CLES_OUI_NON:
        texte += SUFFIXE_OUI_NON
    elif cle in CLES_RETOUR:
        texte += "\n\n0 = Menu"
    return texte


def a_fabriquer():
    """(clé, texte à lire) pour tout ce qui doit avoir une voix."""
    for cle in TEXTES:
        yield cle, texte_a_lire(cle)
    for passage in RAG().passages:
        yield cle_passage(passage), nettoyer_markdown(passage)


def main():
    refaire = "--refaire" in sys.argv
    dossier = config.DOSSIER_AUDIOS / "fr"
    (dossier / "docs").mkdir(parents=True, exist_ok=True)
    faits, deja, echecs = 0, 0, []

    for cle, texte in a_fabriquer():
        cible = dossier / f"{cle}.ogg"
        if cible.exists() and not refaire:
            deja += 1
            continue
        debut = time.time()
        ogg = reponse_vocale_fr(texte, delai=90)
        if ogg is None:
            echecs.append(cle)
            print(f"❌ {cle}")
            continue
        ogg.replace(cible)
        faits += 1
        print(f"✅ {cle}  ({time.time() - debut:.1f} s)")

    print(f"\n{faits} voix créées, {deja} déjà présentes, {len(echecs)} échecs.")
    if echecs:
        print("Relance le script pour réessayer : " + ", ".join(echecs))


if __name__ == "__main__":
    main()
