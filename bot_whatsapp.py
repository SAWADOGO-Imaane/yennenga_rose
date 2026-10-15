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
import time
import uuid
from xml.sax.saxutils import escape

import requests
import uvicorn
from fastapi import FastAPI, Form, Response
from fastapi.staticfiles import StaticFiles

import config
from audio import EXTENSION_PAR_TYPE, Transcripteur, assembler_audios, fichier_audio, reponse_vocale_fr, synthese_fr
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


CHRONO = threading.local()  # début du traitement du message en cours


def temps_restant() -> float:
    return config.BUDGET_REPONSE_S - (time.time() - getattr(CHRONO, "debut", time.time()))


def etape(nom: str, depart: float):
    print(f"   ⏱️ {nom} : {time.time() - depart:.1f} s")


def construire(reponses: list[Reponse], etat: dict, sortie: list, vocal: bool = False):
    """Ajoute à `sortie` des messages ("texte", contenu) ou ("media", url).

    - Réponse à un VOCAL : UNE seule note vocale qui contient TOUTE la réponse
      (voix prêtes d'audios/<langue>/ collées bout à bout), puis le texte.
      Les morceaux sans voix prête (réponse de l'IA, liste des centres) sont lus
      en direct s'il reste assez de temps avant la limite de 15 s de Twilio.
    - Réponse à un TEXTE en mooré / dioula : audio enregistré de chaque message.
    - Réponse à un TEXTE en français : texte seul."""
    langue = etat.get("langue", "fr")

    if vocal:
        morceaux = []  # chemins d'audio, ou texte à lire en direct
        for r in reponses:
            audio = fichier_audio(r.cle, langue) if r.cle else None
            if audio:
                morceaux.append(audio)
            elif langue == "fr":
                morceaux.append(texte_whatsapp(r))
            else:
                print(f"[Audio] Pas d'audio enregistré pour « {r.cle} » ({langue})")
        manquants = [m for m in morceaux if isinstance(m, str)]
        if manquants:
            delai = temps_restant() - 1.5
            voix = reponse_vocale_fr("\n\n".join(manquants), delai=delai) if delai >= 2 else None
            if voix is None:
                print(f"[Audio] Voix en direct impossible ({temps_restant():.1f} s restantes) : "
                      f"seules les voix prêtes sont envoyées")
            # la voix fabriquée remplace le premier morceau manquant, les autres sont retirés
            nouveaux, place = [], False
            for m in morceaux:
                if isinstance(m, str):
                    if not place and voix:
                        nouveaux.append(voix)
                        place = True
                else:
                    nouveaux.append(m)
            morceaux = nouveaux
        note = assembler_audios(morceaux)
        if note:
            sortie.append(("media", url_publique(note)))
        sortie.append(("texte", "\n\n".join(texte_whatsapp(r) for r in reponses)))
        return

    textes = []

    def vider():
        if textes:
            sortie.append(("texte", "\n\n".join(textes)))
            textes.clear()

    for r in reponses:
        audio = fichier_audio(r.cle, langue) if (r.cle and langue != "fr") else None
        if audio:
            vider()
            sortie.append(("media", url_publique(audio)))
        textes.append(texte_whatsapp(r))
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
    ext = EXTENSION_PAR_TYPE.get(type_mime.split(";")[0].strip(), ".ogg")
    chemin = config.DOSSIER_TMP / f"wa_{uuid.uuid4().hex}{ext}"
    reponse = requests.get(url, auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN), timeout=30)
    reponse.raise_for_status()
    chemin.write_bytes(reponse.content)
    return chemin


def lien_direct_du_vocal(url: str) -> str:
    """Twilio protège ses vocaux par mot de passe, puis REDIRIGE vers une adresse
    temporaire lisible sans mot de passe. On récupère seulement cette adresse
    (petite requête, sans télécharger l'audio) pour que Groq aille chercher le vocal."""
    r = requests.get(url, auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
                     allow_redirects=False, timeout=6, stream=True)
    r.close()
    lien = r.headers.get("Location")
    if r.status_code in (301, 302, 303, 307, 308) and lien:
        return lien
    raise RuntimeError(f"pas de redirection (code {r.status_code})")


def traiter(numero: str, corps: str, media_url: str | None, media_type: str | None) -> list:
    etat = ETATS.setdefault(numero, {})
    sortie = []
    try:
        if media_url and media_type and media_type.startswith("audio"):
            if "langue" not in etat:
                construire(moteur.traiter(etat, "/start"), etat, sortie, vocal=True)
                return sortie
            langue = etat["langue"]
            transcrit, langue_entendue, fait = None, langue, False
            # 1) Le plus rapide : Groq va chercher le vocal directement chez Twilio
            if transcripteur.utilise_groq() and config.GROQ_PAR_URL and (langue == "fr" or not config.ACTIVER_MMS):
                t = time.time()
                try:
                    url_directe = lien_direct_du_vocal(media_url)
                    etape("lien du vocal", t)
                    t = time.time()
                    transcrit, langue_entendue = transcripteur.transcrire_url(url_directe, langue)
                    fait = True
                    etape("transcription Groq (par adresse)", t)
                except Exception as erreur:
                    print(f"[Audio] Groq ne peut pas lire l'adresse du vocal ({erreur}) : téléchargement")
            # 2) Sinon : on télécharge le vocal puis on le transcrit
            if not fait:
                t = time.time()
                chemin = telecharger_vocal(media_url, media_type)
                etape("téléchargement du vocal", t)
                t = time.time()
                try:
                    transcrit, langue_entendue = transcripteur.transcrire_avec_langue(chemin, langue)
                finally:
                    chemin.unlink(missing_ok=True)
                etape("transcription", t)

            if not transcrit:
                cle = "vocal_langue_locale" if langue in ("mos", "dyu") else "pas_compris_vocal"
                construire([Reponse(texte(cle, langue), cle=cle)], etat, sortie, vocal=True)
                return sortie
            sortie.append(("texte", f"📝 J'ai entendu : « {transcrit} »"))
            # Elle a parlé français alors que le mooré/dioula était choisi : on répond en français
            if langue_entendue == "fr" and langue != "fr":
                etat["langue"] = "fr"
                sortie.append(("texte", "🌐 Vous parlez français : je continue en français. "
                                        "(Tapez 0 puis 7 pour changer de langue.)"))
            t = time.time()
            reponses = moteur.traiter(etat, transcrit, vocal_langue=langue_entendue)
            etape("réponse (menu ou IA)", t)
            t = time.time()
            construire(reponses, etat, sortie, vocal=True)
            etape("voix", t)
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
    debut = time.time()
    CHRONO.debut = debut
    sortie = traiter(From, Body, MediaUrl0 if NumMedia else None, MediaContentType0)
    duree = time.time() - debut
    genre = "vocal" if NumMedia else "texte"
    alerte = "  ⚠️ TROP LENT : Twilio abandonne après 15 s" if duree > 14 else ""
    print(f"[WhatsApp] Réponse à un {genre} en {duree:.1f} s{alerte}")
    return Response(content=en_twiml(sortie), media_type="application/xml")


@app.get("/")
def accueil():
    return {"statut": "Yennenga Rose WhatsApp fonctionne 🌸"}


if __name__ == "__main__":
    manquants = [n for n in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "PUBLIC_URL") if not getattr(config, n)]
    if manquants:
        raise SystemExit(f"❌ À remplir dans .env : {', '.join(manquants)}")
    # Whisper local : chargé dès le démarrage pour que le 1er vocal ne dépasse pas 15 s
    try:
        if transcripteur.utilise_groq():
            print("[Audio] Transcription des vocaux : Groq " + config.GROQ_WHISPER_MODEL)
        else:
            transcripteur._charger_whisper()
    except Exception as erreur:
        print(f"[Audio] Whisper non chargé ({erreur}) : les vocaux en français ne seront pas compris.")
    uvicorn.run(app, host="0.0.0.0", port=8000)
