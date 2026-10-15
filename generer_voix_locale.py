"""
Fabrique les voix en MOORÉ (ou DIOULA) avec le modèle de synthèse vocale de Meta :
    facebook/mms-tts-mos   (mooré)
    facebook/mms-tts-dyu   (dioula)

Le bot sait déjà envoyer ces voix : il cherche audios/<langue>/<clé>.ogg.

Étapes :
  1) Les traductions écrites sont dans data/traductions_<langue>.json  { "clé": "texte en mooré" }
     - soit l'équipe les écrit (le mieux),
     - soit on fait un BROUILLON automatique avec --traduire (modèle NLLB de Meta),
       que des locutrices DOIVENT relire et corriger avant la démo.
  2) Ce script lit chaque traduction et fabrique audios/<langue>/<clé>.ogg

Commandes :
  python generer_voix_locale.py --langue mos --traduire   (brouillon des traductions manquantes)
  python generer_voix_locale.py --langue mos              (fabrique les voix)
  python generer_voix_locale.py --langue mos --refaire    (refait toutes les voix)
  python generer_voix_locale.py --langue mos --cle menu   (une seule voix, pour tester)

⚠️ Le modèle ne lit que des lettres : écrire les chiffres EN TOUTES LETTRES en mooré
   (« yembre », « yiibu »…) sinon ils disparaissent de la voix.
Installation (une fois, ~2 Go) :  pip install torch transformers sentencepiece scipy
"""
import argparse
import json
import re
import subprocess
import sys
import uuid

import config
from textes import TEXTES

MODELES_TTS = {"mos": "facebook/mms-tts-mos", "dyu": "facebook/mms-tts-dyu"}
CODES_NLLB = {"mos": "mos_Latn", "dyu": "dyu_Latn"}
MODELE_NLLB = "facebook/nllb-200-distilled-600M"
IGNORER = {"choix_langue"}  # audio spécial dans les 3 langues : audios/commun/choix_langue.ogg


def fichier_traductions(langue):
    return config.RACINE / "data" / f"traductions_{langue}.json"


def lire_traductions(langue) -> dict:
    try:
        return json.loads(fichier_traductions(langue).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def ecrire_traductions(langue, traductions: dict):
    fichier_traductions(langue).write_text(
        json.dumps(traductions, ensure_ascii=False, indent=2), encoding="utf-8")


def nettoyer(texte: str) -> str:
    """Enlève emojis, puces et symboles que la voix ne sait pas lire."""
    texte = re.sub(r"[^\w\s'’.,;:!?()\-]", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


def phrases(texte: str) -> list[str]:
    """Coupe en phrases courtes : le modèle lit mieux des morceaux courts."""
    morceaux = re.split(r"(?<=[.!?:;])\s+|\n+", texte)
    return [nettoyer(m) for m in morceaux if nettoyer(m)]


# ---------------------------------------------------------------
# 1) Brouillon de traduction (NLLB)
# ---------------------------------------------------------------
def traduire(langue: str, refaire: bool):
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    traductions = lire_traductions(langue)
    a_faire = [c for c in TEXTES if c not in IGNORER and (refaire or not traductions.get(c))]
    if not a_faire:
        print("✅ Toutes les traductions existent déjà.")
        return
    print(f"Chargement de {MODELE_NLLB} (la 1re fois : téléchargement ~2,5 Go)…")
    tok = AutoTokenizer.from_pretrained(MODELE_NLLB, src_lang="fra_Latn")
    modele = AutoModelForSeq2SeqLM.from_pretrained(MODELE_NLLB)
    cible = tok.convert_tokens_to_ids(CODES_NLLB[langue])

    for cle in a_faire:
        lignes = []
        for ligne in TEXTES[cle].split("\n"):
            propre = nettoyer(ligne)
            if not propre:
                continue
            entrees = tok(propre, return_tensors="pt")
            sortie = modele.generate(**entrees, forced_bos_token_id=cible, max_new_tokens=200)
            lignes.append(tok.batch_decode(sortie, skip_special_tokens=True)[0])
        traductions[cle] = "\n".join(lignes)
        print(f"  📝 {cle} : {traductions[cle][:70]}…")
        ecrire_traductions(langue, traductions)  # sauvegarde au fur et à mesure
    print(f"\n✅ Brouillon écrit dans {fichier_traductions(langue)}")
    print("⚠️ À FAIRE RELIRE ET CORRIGER par une locutrice avant de fabriquer les voix.")


# ---------------------------------------------------------------
# 2) Synthèse vocale (MMS-TTS)
# ---------------------------------------------------------------
def fabriquer_voix(langue: str, refaire: bool, seule_cle: str | None):
    import numpy as np
    import torch
    from scipy.io import wavfile
    from transformers import AutoTokenizer, VitsModel

    traductions = lire_traductions(langue)
    if not traductions:
        sys.exit(f"❌ Aucune traduction dans {fichier_traductions(langue)}. "
                 f"Lance d'abord : python generer_voix_locale.py --langue {langue} --traduire")

    dossier = config.DOSSIER_AUDIOS / langue
    dossier.mkdir(parents=True, exist_ok=True)
    cles = [seule_cle] if seule_cle else [c for c in traductions if c not in IGNORER]

    print(f"Chargement de {MODELES_TTS[langue]}…")
    tok = AutoTokenizer.from_pretrained(MODELES_TTS[langue])
    modele = VitsModel.from_pretrained(MODELES_TTS[langue])
    taux = modele.config.sampling_rate
    vocab = set(tok.get_vocab())
    silence = np.zeros(int(taux * 0.4), dtype=np.float32)

    faites = 0
    for cle in cles:
        texte = traductions.get(cle, "").strip()
        sortie = dossier / f"{cle}.ogg"
        if not texte:
            print(f"  ⏭️  {cle} : pas de traduction")
            continue
        if sortie.exists() and not refaire:
            continue
        # Lettres que le modèle ne connaît pas (elles seront sautées)
        inconnues = {ch for ch in texte.lower() if ch.isalpha() and ch not in vocab}
        if inconnues:
            print(f"  ⚠️ {cle} : lettres inconnues du modèle, ignorées : {' '.join(sorted(inconnues))}")

        morceaux = []
        for phrase in phrases(texte):
            entrees = tok(phrase, return_tensors="pt")
            if entrees["input_ids"].shape[-1] == 0:
                continue
            with torch.no_grad():
                onde = modele(**entrees).waveform[0].numpy()
            morceaux += [onde, silence]
        if not morceaux:
            print(f"  ❌ {cle} : rien à lire")
            continue

        wav = config.DOSSIER_TMP / f"{uuid.uuid4().hex}.wav"
        wavfile.write(wav, taux, np.concatenate(morceaux).astype(np.float32))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", "48000",
                        "-c:a", "libopus", "-b:a", "32k", str(sortie)], check=True)
        wav.unlink(missing_ok=True)
        faites += 1
        print(f"  🔊 {cle}")
    print(f"\n✅ {faites} voix fabriquées dans {dossier}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Voix mooré / dioula avec MMS-TTS")
    p.add_argument("--langue", choices=["mos", "dyu"], default="mos")
    p.add_argument("--traduire", action="store_true", help="brouillon de traduction automatique (NLLB)")
    p.add_argument("--refaire", action="store_true", help="refaire même ce qui existe déjà")
    p.add_argument("--cle", help="ne traiter qu'une clé (ex. menu)")
    a = p.parse_args()
    if a.traduire:
        traduire(a.langue, a.refaire)
    else:
        fabriquer_voix(a.langue, a.refaire, a.cle)
