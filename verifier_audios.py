"""
Prépare les enregistrements audio.

    python verifier_audios.py

- Crée TEXTES_A_ENREGISTRER.md : la liste des messages à traduire et enregistrer,
  avec le nom exact du fichier à créer pour chaque langue.
- Affiche les audios déjà présents et ceux qui manquent.
"""
import config
from audio import fichier_audio
from textes import TEXTES

LANGUES_AUDIO = {"mos": "Mooré", "dyu": "Dioula", "fr": "Français (optionnel)"}

# Messages les plus importants : à enregistrer en priorité
PRIORITAIRES = [
    "choix_langue", "bienvenue", "menu", "autopalpation", "signes_alerte",
    "questionnaire_intro", "q_boule", "q_peau", "q_ecoulement", "q_mamelon", "q_forme",
    "q_plaie", "q_douleur", "q_famille", "q_age", "reponse_oui_non",
    "resultat_consulter", "resultat_depistage", "resultat_surveillance",
    "demande_ville", "centres_intro", "centres_autre",
]


def generer_fiche():
    lignes = [
        "# Messages à enregistrer — Yennenga Rose\n",
        "Conseils : enregistrer au calme, téléphone à 20 cm, voix lente et chaleureuse.",
        "Format idéal : message vocal WhatsApp/Telegram exporté (.ogg / .opus) ou .mp3.",
        "Le message `choix_langue` est spécial : une seule voix ou plusieurs, qui dit la phrase",
        "dans les 3 langues à la suite → `audios/commun/choix_langue.ogg`.\n",
        "Pour le menu et les centres, dire aussi les chiffres (« pour …, appuyez sur 1 »).\n",
    ]
    for cle in sorted(TEXTES, key=lambda c: (c not in PRIORITAIRES, PRIORITAIRES.index(c) if c in PRIORITAIRES else 0)):
        prio = "⭐ PRIORITAIRE" if cle in PRIORITAIRES else "secondaire"
        lignes.append(f"## `{cle}` — {prio}\n")
        lignes.append(TEXTES[cle] + "\n")
        if cle == "choix_langue":
            lignes.append("Fichier : `audios/commun/choix_langue.ogg`\n")
        else:
            lignes.append("Fichiers : " + ", ".join(f"`audios/{l}/{cle}.ogg`" for l in LANGUES_AUDIO) + "\n")
    chemin = config.RACINE / "TEXTES_A_ENREGISTRER.md"
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    return chemin


def bilan():
    print("\nÉtat des audios :")
    for code, nom in LANGUES_AUDIO.items():
        presents = [c for c in TEXTES if fichier_audio(c, code)]
        manquants_prio = [c for c in PRIORITAIRES if not fichier_audio(c, code)]
        print(f"\n  {nom} : {len(presents)}/{len(TEXTES)} audios")
        if code != "fr" and manquants_prio:
            print("    Prioritaires manquants : " + ", ".join(manquants_prio))


if __name__ == "__main__":
    print(f"Fiche créée : {generer_fiche()}")
    bilan()
