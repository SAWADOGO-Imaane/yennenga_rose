"""
Bot WhatsApp Yennenga Rose (via le sandbox WhatsApp de Twilio).
Utilise le même moteur que la démo web.

Les réponses sont renvoyées DIRECTEMENT dans la réponse au webhook (TwiML),
ce qui fonctionne avec un compte d'essai Twilio (pas besoin de modèle pré-approuvé).

Lancer :  python bot_whatsapp.py      (serveur sur le port 8000)
Puis exposer le port avec ngrok, et coller https://<adresse-ngrok>/whatsapp
dans Sandbox settings → "When a message comes in" (POST).
"""
import json
import mimetypes
import threading
import uuid
from xml.sax.saxutils import escape

import requests
import uvicorn
from fastapi import FastAPI, Form, Response
from fastapi.staticfiles import StaticFiles

import config
from audio import Transcripteur, fichier_audio, synthese_fr
from centres import Centres
from moteur import CLAVIER_OUI_NON, CLAVIER_RETOUR, Moteur, Reponse
from rag import RAG
from textes import texte

moteur = Moteur(RAG(), Centres())
transcripteur = Transcripteur()

app = FastAPI(title="Yennenga Rose WhatsApp")
# Twilio doit pouvoir télécharger nos audios : on les sert publiquement
app.mount("/audios", StaticFiles(directory=config.DOSSIER_AUDIOS), name="audios")
app.mount("/tmp", StaticFiles(directory=config.DOSSIER_TMP), name="tmp")

# ---------------------------------------------------------------
# État des conversations (une entrée par numéro), sauvegardé en JSON
# ---------------------------------------------------------------
FICHIER_ETATS = config.RACINE / "data" / "etat_whatsapp.json"
verrou = threading.Lock()
try:
    ETATS = json.loads(FICHIER_ETATS.read_text(encoding="utf-8"))
except (FileNotFoundError, json.JSONDecodeError):
    ETATS = {}


def sauvegarder():
    with verrou:
        FICHIER_ETATS.write_text(json.dumps(ETATS, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------
# Construction des messages de réponse
# ---------------------------------------------------------------
def url_publique(chemin) -> str:
    relatif = chemin.relative_to(config.RACINE).as_posix()
    return f"{config.PUBLIC_URL.rstrip('/')}/{relatif}"


RAPPEL_WHATSAPP = (
    "🔔 Les rappels automatiques arrivent bientôt. En attendant, notez une date chaque mois "
    "(par exemple le 1er) et revenez ici : tapez 1 pour revoir comment examiner vos seins."
)


def texte_whatsapp(r: Reponse) -> str:
    """WhatsApp n'a pas de boutons : on écrit les choix en clair."""
    if r.action in ("rappel_on", "rappel_off"):
        return RAPPEL_WHATSAPP
    if r.clavier == CLAVIER_OUI_NON:
        return r.texte + "\n\n1 = Oui   ·   2 = Non   ·   0 = Menu"
    if r.clavier == CLAVIER_RETOUR:
        return r.texte + "\n\n0 = Menu"
    return r.texte


def construire(reponses: list[Reponse], etat: dict, sortie: list):
    """Ajoute à `sortie` des messages ("texte", contenu) ou ("media", url).
    Les textes consécutifs sont regroupés ; un audio part toujours seul."""
    langue = etat.get("langue", "fr")
    textes = []

    def vider():
        if textes:
            sortie.append(("texte", "\n\n".join(textes)))
            textes.clear()

    for r in reponses:
        audio = fichier_audio(r.cle, langue) if r.cle else None
        if audio:
            vider()
            sortie.append(("media", url_publique(audio)))
        textes.append(texte_whatsapp(r))

        if r.lire_a_voix_haute and langue == "fr":
            mp3 = synthese_fr(r.texte)
            if mp3:
                vider()
                sortie.append(("media", url_publique(mp3)))
    vider()


def en_twiml(sortie: list) -> str:
    morceaux = []
    for genre, contenu in sortie:
        if genre == "texte":
            morceaux.append(f"<Message><Body>{escape(contenu[:1600])}</Body></Message>")
        else:
            morceaux.append(f"<Message><Media>{escape(contenu)}</Media></Message>")
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + "".join(morceaux) + "</Response>"


# ---------------------------------------------------------------
# Traitement d'un message reçu
# ---------------------------------------------------------------
def telecharger_vocal(url: str, type_mime: str):
    ext = mimetypes.guess_extension(type_mime.split(";")[0]) or ".ogg"
    chemin = config.DOSSIER_TMP / f"wa_{uuid.uuid4().hex}{ext}"
    reponse = requests.get(url, auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN), timeout=30)
    reponse.raise_for_status()
    chemin.write_bytes(reponse.content)
    return chemin


def traiter(numero: str, corps: str, media_url: str | None, media_type: str | None) -> list:
    etat = ETATS.setdefault(numero, {})
    sortie = []
    try:
        if media_url and media_type and media_type.startswith("audio"):
            if "langue" not in etat:
                construire(moteur.traiter(etat, "/start"), etat, sortie)
                return sortie
            langue = etat["langue"]
            chemin = telecharger_vocal(media_url, media_type)
            try:
                transcrit = transcripteur.transcrire(chemin, langue)
            finally:
                chemin.unlink(missing_ok=True)

            if not transcrit:
                cle = "vocal_langue_locale" if langue in ("mos", "dyu") else "pas_compris_vocal"
                construire([Reponse(texte(cle, langue), cle=cle)], etat, sortie)
                return sortie
            sortie.append(("texte", f"📝 J'ai entendu : « {transcrit} »"))
            construire(moteur.traiter(etat, transcrit, vocal_langue=langue), etat, sortie)
        elif corps.strip():
            construire(moteur.traiter(etat, corps), etat, sortie)
        else:  # image, sticker... : on remet le menu
            construire(moteur.traiter(etat, "menu"), etat, sortie)
    except Exception as erreur:
        print(f"[WhatsApp] Erreur pour {numero[-4:]} : {erreur}")
        sortie = [("texte", "Désolée, un problème est survenu. Tapez 0 pour revenir au menu.")]
    finally:
        sauvegarder()
    return sortie


# ---------------------------------------------------------------
# Webhook appelé par Twilio à chaque message reçu
# ---------------------------------------------------------------
@app.post("/whatsapp")
def webhook(
    From: str = Form(...),
    Body: str = Form(""),
    NumMedia: int = Form(0),
    MediaUrl0: str | None = Form(None),
    MediaContentType0: str | None = Form(None),
):
    # Twilio attend la réponse au maximum 15 secondes.
    sortie = traiter(From, Body, MediaUrl0 if NumMedia else None, MediaContentType0)
    return Response(content=en_twiml(sortie), media_type="application/xml")


@app.get("/")
def accueil():
    return {"statut": "Yennenga Rose WhatsApp fonctionne 🌸"}


if __name__ == "__main__":
    manquants = [n for n in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "PUBLIC_URL") if not getattr(config, n)]
    if manquants:
        raise SystemExit(f"❌ À remplir dans .env : {', '.join(manquants)}")
    # Charge Whisper dès le démarrage pour que le 1er vocal ne dépasse pas 15 s
    try:
        transcripteur._charger_whisper()
    except Exception as erreur:
        print(f"[Audio] Whisper non chargé ({erreur}) : les vocaux en français ne seront pas compris.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
