"""
Tout ce qui concerne l'audio :
- retrouver les messages pré-enregistrés (audios/<langue>/<clé>.ogg)
- transcrire les vocaux : Whisper (français), MMS de Meta (mooré / dioula, expérimental)
- synthèse vocale optionnelle des réponses libres en français (gTTS)
"""
import re
import subprocess
import time
import uuid
from pathlib import Path

import config

EXTENSIONS = (".ogg", ".opus", ".mp3", ".m4a", ".wav")
EXTENSIONS_GROQ = (".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".opus", ".wav", ".webm")

# Type de fichier envoyé par WhatsApp -> extension (Windows devine parfois mal)
EXTENSION_PAR_TYPE = {"audio/ogg": ".ogg", "audio/opus": ".opus", "audio/mpeg": ".mp3",
                      "audio/mp4": ".m4a", "audio/aac": ".m4a", "audio/amr": ".amr",
                      "audio/wav": ".wav", "audio/webm": ".webm"}

# Code de langue MMS : mooré = "mos", dioula = "dyu"
CODES_MMS = {"mos": "mos", "dyu": "dyu"}


# ---------------------------------------------------------------
# Messages pré-enregistrés
# ---------------------------------------------------------------
def fichier_audio(cle: str, langue: str) -> Path | None:
    """Cherche audios/<langue>/<cle>.* puis audios/commun/<cle>.*"""
    for dossier in (langue, "commun"):
        for ext in EXTENSIONS:
            chemin = config.DOSSIER_AUDIOS / dossier / f"{cle}{ext}"
            if chemin.exists():
                return chemin
    return None


# ---------------------------------------------------------------
# Conversion : n'importe quel audio -> WAV 16 kHz mono (exigé par MMS)
# ---------------------------------------------------------------
def en_wav_16k(chemin: Path) -> Path:
    sortie = config.DOSSIER_TMP / f"{uuid.uuid4().hex}.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(chemin), "-ac", "1", "-ar", "16000", str(sortie)],
        check=True,
    )
    return sortie


# ---------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------
class Transcripteur:
    """Les modèles sont chargés au premier vocal (le bot démarre plus vite)."""

    def __init__(self):
        self._whisper = None
        self._groq = None
        self._mms_modele = None
        self._mms_processeur = None
        self._mms_langue = None

    # --- Français : Whisper ---
    def _charger_whisper(self):
        if self._whisper is None:
            from faster_whisper import WhisperModel
            print(f"[Audio] Chargement de Whisper '{config.WHISPER_MODEL}'…")
            self._whisper = WhisperModel(config.WHISPER_MODEL, device="auto", compute_type="int8")
        return self._whisper

    def transcrire_fr_local(self, chemin: Path) -> str:
        segments, _ = self._charger_whisper().transcribe(str(chemin), language="fr", beam_size=5)
        return " ".join(s.text.strip() for s in segments).strip()

    # --- Whisper via l'API Groq (rapide, ~1 s, ne charge pas le PC) ---
    def utilise_groq(self) -> bool:
        return config.TRANSCRIPTION == "groq" and bool(config.LLM_API_KEY) and "groq" in config.LLM_BASE_URL

    def _client_groq(self):
        if self._groq is None:
            from openai import OpenAI
            self._groq = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL,
                                timeout=8, max_retries=0)
        return self._groq

    def _transcrire_groq(self, chemin: Path, langue: str | None):
        """Renvoie (texte, langue détectée en minuscules)."""
        params = {"model": config.GROQ_WHISPER_MODEL, "response_format": "verbose_json"}
        if langue:
            params["language"] = langue
        # Groq refuse certaines extensions (ex. ".oga" donné par Windows) : on impose un nom valide
        ext = chemin.suffix.lower()
        if ext not in EXTENSIONS_GROQ:
            ext = ".ogg"
        with open(chemin, "rb") as f:
            r = self._client_groq().audio.transcriptions.create(
                file=(f"vocal{ext}", f.read()), **params)
        texte = (getattr(r, "text", "") or "").strip()
        langue_detectee = (getattr(r, "language", "") or langue or "").lower()
        return texte, langue_detectee

    def _groq_par_url(self, url: str, langue: str | None):
        """Groq télécharge LUI-MÊME le vocal (serveur à serveur) : évite au PC
        de télécharger puis renvoyer le fichier. Renvoie (texte, langue)."""
        import requests
        donnees = {"model": config.GROQ_WHISPER_MODEL, "url": url, "response_format": "verbose_json"}
        if langue:
            donnees["language"] = langue
        r = requests.post(
            f"{config.LLM_BASE_URL.rstrip('/')}/audio/transcriptions",
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            files={k: (None, v) for k, v in donnees.items()},
            timeout=8,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code} {r.text[:200]}")
        j = r.json()
        return (j.get("text") or "").strip(), (j.get("language") or langue or "").lower()

    def transcrire_url(self, url: str, langue: str) -> tuple[str | None, str]:
        """Comme transcrire_avec_langue, mais à partir de l'adresse du vocal.
        Lève une exception si Groq ne peut pas lire l'adresse (on téléchargera alors)."""
        if langue == "fr":
            return self._groq_par_url(url, "fr")[0] or None, "fr"
        texte, detectee = self._groq_par_url(url, None)
        print(f"[Audio] Langue détectée (Groq) : {detectee}")
        if detectee.startswith("fr") and texte:
            return texte, "fr"
        return None, langue

    def transcrire_fr(self, chemin: Path) -> str:
        if self.utilise_groq():
            try:
                return self._transcrire_groq(chemin, "fr")[0]
            except Exception as erreur:
                print(f"[Audio] Groq indisponible ({erreur}), Whisper local à la place")
        return self.transcrire_fr_local(chemin)

    # --- Mooré / dioula : MMS (expérimental) ---
    def _charger_mms(self, langue: str):
        from transformers import AutoProcessor, Wav2Vec2ForCTC

        if self._mms_modele is None:
            print(f"[Audio] Chargement de MMS '{config.MMS_MODEL}' (peut prendre plusieurs minutes)…")
            self._mms_processeur = AutoProcessor.from_pretrained(config.MMS_MODEL)
            self._mms_modele = Wav2Vec2ForCTC.from_pretrained(config.MMS_MODEL)
        if self._mms_langue != langue:
            code = CODES_MMS[langue]
            self._mms_processeur.tokenizer.set_target_lang(code)
            self._mms_modele.load_adapter(code)
            self._mms_langue = langue

    def transcrire_local(self, chemin: Path, langue: str) -> str:
        import soundfile as sf
        import torch

        self._charger_mms(langue)
        wav = en_wav_16k(chemin)
        try:
            signal, _ = sf.read(str(wav))
            entrees = self._mms_processeur(signal, sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                logits = self._mms_modele(**entrees).logits
            ids = torch.argmax(logits, dim=-1)[0]
            return self._mms_processeur.decode(ids).strip()
        finally:
            wav.unlink(missing_ok=True)

    # --- Point d'entrée ---
    def transcrire(self, chemin: Path, langue: str) -> str | None:
        """Renvoie le texte transcrit, ou None si la transcription est impossible."""
        return self.transcrire_avec_langue(chemin, langue)[0]

    def detecter_francais(self, chemin: Path) -> str | None:
        """Whisper sans langue imposée : renvoie le texte seulement s'il entend du français."""
        if self.utilise_groq():
            try:
                texte, langue = self._transcrire_groq(chemin, None)
                print(f"[Audio] Langue détectée (Groq) : {langue}")
                return texte if langue.startswith("fr") and texte else None
            except Exception as erreur:
                print(f"[Audio] Groq indisponible ({erreur}), Whisper local à la place")
        segments, info = self._charger_whisper().transcribe(str(chemin), beam_size=5)
        texte = " ".join(s.text.strip() for s in segments).strip()
        print(f"[Audio] Langue détectée : {info.language} ({info.language_probability:.0%})")
        if info.language == "fr" and info.language_probability >= 0.6 and texte:
            return texte
        return None

    def transcrire_avec_langue(self, chemin: Path, langue: str) -> tuple[str | None, str]:
        """Renvoie (texte, langue réellement entendue).
        Si la langue choisie est le mooré ou le dioula mais que la personne parle
        français, on le détecte et on transcrit quand même en français."""
        try:
            if langue == "fr":
                return self.transcrire_fr(chemin), "fr"
            if config.ACTIVER_MMS and langue in CODES_MMS:
                return self.transcrire_local(chemin, langue), langue
            texte_fr = self.detecter_francais(chemin)
            if texte_fr:
                return texte_fr, "fr"
        except Exception as erreur:
            print(f"[Audio] Échec de transcription ({langue}) : {erreur}")
        return None, langue


# ---------------------------------------------------------------
# Synthèse vocale (français uniquement, optionnelle)
# ---------------------------------------------------------------
def synthese_fr(texte: str) -> Path | None:
    if not config.ACTIVER_TTS_FR:
        return None
    try:
        from gtts import gTTS
        chemin = config.DOSSIER_TMP / f"{uuid.uuid4().hex}.mp3"
        gTTS(texte, lang="fr").save(str(chemin))
        return chemin
    except Exception as erreur:
        print(f"[Audio] Synthèse vocale impossible : {erreur}")
        return None


# ---------------------------------------------------------------
# Réponse vocale à un message vocal (français, voix de synthèse)
# ---------------------------------------------------------------
def texte_pour_voix(texte: str) -> str:
    """Rend le texte agréable à écouter : sans emojis, avec des consignes parlées."""
    t = re.sub(r"(\d+)\s*=\s*", r"tapez \1 pour ", texte)          # "1 = Oui" -> "tapez 1 pour Oui"
    t = re.sub(r"^\s*(\d+)\s+(?=\D)", r"Tapez \1 pour : ", t, flags=re.M)  # lignes du menu
    t = re.sub(r"[^\w\s.,;:!?'’()\-«»%/àâäéèêëîïôöùûüçœÀÂÉÈÊËÎÏÔÖÙÛÜÇŒ]", " ", t)  # emojis, puces
    t = t.replace("·", ",")
    return re.sub(r"[ \t]+", " ", t).strip()


def nettoyer_tmp(age_max_s: int = 3600):
    """Supprime les fichiers audio temporaires de plus d'une heure."""
    limite = time.time() - age_max_s
    for f in config.DOSSIER_TMP.glob("*"):
        try:
            if f.is_file() and f.stat().st_mtime < limite:
                f.unlink()
        except OSError:
            pass


def assembler_audios(chemins: list[Path]) -> Path | None:
    """Colle plusieurs audios en UNE seule note vocale WhatsApp (.ogg Opus).
    Tout se fait sur le PC avec ffmpeg : rapide et sans internet."""
    chemins = [c for c in chemins if c and Path(c).exists()]
    if not chemins:
        return None
    if len(chemins) == 1:
        return Path(chemins[0])
    sortie = config.DOSSIER_TMP / f"note_{uuid.uuid4().hex}.ogg"
    entrees = []
    for c in chemins:
        entrees += ["-i", str(c)]
    flux = "".join(f"[{i}:a]" for i in range(len(chemins)))
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *entrees,
             "-filter_complex", f"{flux}concat=n={len(chemins)}:v=0:a=1[a]", "-map", "[a]",
             "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "32k", str(sortie)],
            check=True, timeout=10,
        )
        return sortie
    except Exception as erreur:
        print(f"[Audio] Assemblage impossible ({erreur}) : premier audio seul")
        return Path(chemins[0])


def _voix_edge(texte: str, mp3: Path, delai: float):
    """Voix neuronale Microsoft Edge (gratuite, une seule connexion : rapide)."""
    import asyncio
    import edge_tts

    async def generer():
        await edge_tts.Communicate(texte, config.VOIX_EDGE, rate="-5%").save(str(mp3))

    asyncio.run(asyncio.wait_for(generer(), timeout=delai))


def _voix_gtts(texte: str, mp3: Path):
    """Voix Google (secours) : une requête par tranche de ~100 caractères, donc plus lente."""
    from gtts import gTTS
    gTTS(texte, lang="fr", tld="fr", timeout=5).save(str(mp3))


def reponse_vocale_fr(texte: str, delai: float = 8.0) -> Path | None:
    """Texte -> note vocale WhatsApp (.ogg Opus) en moins de `delai` secondes.
    None si impossible ou trop lent (la réponse écrite part quand même)."""
    if not config.REPONSE_VOCALE or delai < 2:
        return None
    nettoyer_tmp()
    a_lire = texte_pour_voix(texte)
    mp3 = config.DOSSIER_TMP / f"voix_{uuid.uuid4().hex}.mp3"
    debut = time.time()
    try:
        try:
            _voix_edge(a_lire, mp3, delai)
            moteur_voix = "edge-tts"
        except Exception as erreur:
            reste = delai - (time.time() - debut)
            if reste < 3:
                raise TimeoutError(f"edge-tts trop lent ({erreur})")
            print(f"[Audio] edge-tts indisponible ({erreur}), gTTS à la place")
            _voix_gtts(a_lire, mp3)
            moteur_voix = "gTTS"
        ogg = mp3.with_suffix(".ogg")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
             "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "32k", str(ogg)],
            check=True,
        )
        print(f"[Audio] Voix {moteur_voix} : {time.time() - debut:.1f} s")
        return ogg
    except Exception as erreur:
        print(f"[Audio] Réponse vocale abandonnée : {erreur}")
        return None
    finally:
        mp3.unlink(missing_ok=True)
