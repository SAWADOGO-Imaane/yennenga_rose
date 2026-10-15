"""
Serveur de l'APPLICATION Yennenga Rose (mobile + web), sur le même port que WhatsApp.

    python api_app.py        -> port 8000 : WhatsApp (/whatsapp) + application (/api/...)

Un seul serveur, une seule adresse ngrok : le bot WhatsApp continue de marcher.

Routes de l'application :
    POST /api/message   {id, texte}                 -> réponses du bot
    POST /api/vocal     id + fichier audio          -> ce qui a été entendu + réponses + note vocale
    POST /api/analyse   id + photo(s) ou 1 vidéo    -> analyse visuelle d'orientation + centres
    GET  /api/son/...   un audio du bot converti en MP3 (lisible sur iPhone)
"""
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path

import uvicorn
from fastapi import File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import bot_whatsapp as base          # même moteur, même transcription, même serveur
import config
import vision
from audio import EXTENSION_PAR_TYPE, assembler_audios, fichier_audio, reponse_vocale_fr
from moteur import CLAVIER_MENU, Reponse
from textes import TEXTES

app = base.app
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FICHIER_ETATS = config.RACINE / "data" / "etat_app.json"
verrou = threading.Lock()
try:
    ETATS = json.loads(FICHIER_ETATS.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    ETATS = {}


def sauvegarder():
    with verrou:
        FICHIER_ETATS.write_text(json.dumps(ETATS, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------
# Mise en forme des réponses pour l'application
# ---------------------------------------------------------------
LIGNES_MENU = [l for l in TEXTES["menu"].splitlines() if l[:1].isdigit()]


def lien_son(chemin: Path | None) -> str | None:
    """Adresse (relative) d'un audio, servi en MP3 par /api/son/."""
    if not chemin:
        return None
    return "/api/son/" + Path(chemin).resolve().relative_to(config.RACINE).as_posix()


def choix_de(r: Reponse) -> list[dict]:
    """Boutons : [{"valeur": "1", "libelle": "1 🖐️ Apprendre à examiner mes seins"}, ...]"""
    if not r.clavier:
        return []
    libelles = LIGNES_MENU if r.clavier == CLAVIER_MENU else r.clavier
    boutons = []
    for libelle in libelles:
        valeur = libelle.split()[0].strip(".=")
        boutons.append({"valeur": valeur, "libelle": libelle})
    return boutons


def en_json(reponses: list[Reponse], langue: str) -> list[dict]:
    messages = []
    for r in reponses:
        texte = r.texte
        if r.clavier:  # les choix numérotés deviennent des boutons : on les retire du texte
            texte = "\n".join(l for l in texte.splitlines() if not l.strip()[:1].isdigit()).strip()
        audio = fichier_audio(r.cle, langue) if r.cle else None
        messages.append({"texte": texte, "audio": lien_son(audio), "choix": choix_de(r)})
    return messages


def langue_de(etat: dict) -> str:
    return etat.get("langue", "fr")


# ---------------------------------------------------------------
# Routes
# ---------------------------------------------------------------
@app.post("/api/message")
async def api_message(donnees: dict):
    ident = str(donnees.get("id") or "")
    if not ident:
        raise HTTPException(400, "id manquant")
    etat = ETATS.setdefault("app:" + ident, {})
    reponses = base.moteur.traiter(etat, str(donnees.get("texte", "")))
    sauvegarder()
    return {"messages": en_json(reponses, langue_de(etat)), "langue": langue_de(etat)}


def enregistrer(fichier: UploadFile, defaut: str) -> Path:
    ext = Path(fichier.filename or "").suffix.lower() or EXTENSION_PAR_TYPE.get(
        (fichier.content_type or "").split(";")[0], defaut)
    chemin = config.DOSSIER_TMP / f"app_{uuid.uuid4().hex}{ext}"
    chemin.write_bytes(fichier.file.read())
    return chemin


def note_vocale(reponses: list[Reponse], langue: str) -> Path | None:
    """UNE note vocale avec toute la réponse : voix prêtes + voix fabriquée pour le reste."""
    morceaux, a_lire = [], []
    for r in reponses:
        audio = fichier_audio(r.cle, langue) if r.cle else None
        if audio:
            morceaux.append(audio)
        elif langue == "fr":
            morceaux.append(None)  # place de la voix fabriquée
            a_lire.append(r.texte)
    if a_lire:
        voix = reponse_vocale_fr("\n\n".join(a_lire), delai=20)
        premiere = morceaux.index(None)
        morceaux = [m for m in morceaux if m is not None]
        if voix:
            morceaux.insert(premiere, voix)
    return assembler_audios(morceaux)


@app.post("/api/vocal")
def api_vocal(id: str = Form(...), fichier: UploadFile = File(...)):
    etat = ETATS.setdefault("app:" + id, {})
    if "langue" not in etat:
        reponses = base.moteur.traiter(etat, "/start")
        return {"entendu": None, "messages": en_json(reponses, "fr"), "note": None}
    chemin = enregistrer(fichier, ".m4a")
    debut = time.time()
    try:
        transcrit, langue_entendue = base.transcripteur.transcrire_avec_langue(chemin, etat["langue"])
    finally:
        chemin.unlink(missing_ok=True)
    if not transcrit:
        cle = "vocal_langue_locale" if etat["langue"] in ("mos", "dyu") else "pas_compris_vocal"
        reponses = [base.moteur._msg(etat, cle)]
        return {"entendu": None, "messages": en_json(reponses, langue_de(etat)),
                "note": lien_son(fichier_audio(cle, langue_de(etat)))}
    if langue_entendue == "fr" and etat["langue"] != "fr":
        etat["langue"] = "fr"
    reponses = base.moteur.traiter(etat, transcrit, vocal_langue=langue_entendue)
    note = note_vocale(reponses, langue_de(etat))
    sauvegarder()
    print(f"[App] Vocal traité en {time.time() - debut:.1f} s")
    return {"entendu": transcrit, "messages": en_json(reponses, langue_de(etat)), "note": lien_son(note)}


@app.post("/api/analyse")
def api_analyse(id: str = Form(...), fichiers: list[UploadFile] = File(...)):
    """Photo(s) ou vidéo -> signes VISIBLES -> orientation (jamais un diagnostic) -> centres."""
    etat = ETATS.setdefault("app:" + id, {})
    etat.setdefault("langue", "fr")
    etat.setdefault("mode", "menu")
    a_supprimer: list[Path] = []
    debut = time.time()
    try:
        images = []
        for f in fichiers[:3]:
            chemin = enregistrer(f, ".jpg")
            a_supprimer.append(chemin)
            est_video = (f.content_type or "").startswith("video") or chemin.suffix in (".mp4", ".mov", ".webm", ".3gp")
            extraites = vision.images_de_la_video(chemin) if est_video else [vision.reduire_image(chemin)]
            a_supprimer += extraites
            images += extraites
        o = vision.orientation(vision.analyser_images(images))
    except Exception as erreur:
        print(f"[Vision] Analyse impossible : {erreur}")
        etat.update(mode="questionnaire", q_index=0, reponses={})
        reponses = [
            Reponse("📷 L'analyse de l'image n'est pas disponible pour le moment. "
                    "Répondez à ces quelques questions à la place :"),
            base.moteur._question(etat),
        ]
        sauvegarder()
        return {"analyse": None, "messages": en_json(reponses, langue_de(etat))}
    finally:
        for chemin in a_supprimer:  # confidentialité : on ne garde AUCUNE image
            chemin.unlink(missing_ok=True)

    print(f"[Vision] {o['issue']} {o['signes']} en {time.time() - debut:.1f} s")
    reponses = [Reponse(vision.message_orientation(o))]
    if o["issue"] == "consulter":
        etat["signes_photo"] = o["questions"]
        reponses += base.moteur._demander_ville(etat)  # « Où me faire examiner » directement
    else:
        reponses += base.moteur._menu(etat)
    sauvegarder()
    return {"analyse": o, "messages": en_json(reponses, langue_de(etat))}


@app.get("/api/son/{chemin:path}")
def api_son(chemin: str):
    """Les notes vocales sont en .ogg (WhatsApp) ; l'iPhone préfère le MP3 : on convertit une fois."""
    source = (config.RACINE / chemin).resolve()
    autorises = (config.DOSSIER_AUDIOS.resolve(), config.DOSSIER_TMP.resolve())
    if not source.is_file() or not any(source.is_relative_to(d) for d in autorises):
        raise HTTPException(404)
    if source.suffix == ".mp3":
        return FileResponse(source, media_type="audio/mpeg")
    cache = config.DOSSIER_TMP / "mp3" / (chemin.replace("/", "_") + ".mp3")
    if not cache.exists() or cache.stat().st_mtime < source.stat().st_mtime:
        cache.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
                        "-ac", "1", "-b:a", "64k", str(cache)], check=True, timeout=30)
    return FileResponse(cache, media_type="audio/mpeg")


if __name__ == "__main__":
    print("🌸 Yennenga Rose : WhatsApp (/whatsapp) + application (/api) sur le port 8000")
    print(f"[Vision] Modèle : {config.VISION_MODEL}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
