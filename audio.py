"""
Tout ce qui concerne l'audio :
- retrouver les messages pré-enregistrés (audios/<langue>/<clé>.ogg)
- transcrire les vocaux : Whisper (français), MMS de Meta (mooré / dioula, expérimental)
- synthèse vocale optionnelle des réponses libres en français (gTTS)
"""
import subprocess
import uuid
from pathlib import Path

import config

EXTENSIONS = (".ogg", ".opus", ".mp3", ".m4a", ".wav")

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

    def transcrire_fr(self, chemin: Path) -> str:
        segments, _ = self._charger_whisper().transcribe(str(chemin), language="fr", beam_size=5)
        return " ".join(s.text.strip() for s in segments).strip()

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
        try:
            if langue == "fr":
                return self.transcrire_fr(chemin)
            if config.ACTIVER_MMS and langue in CODES_MMS:
                return self.transcrire_local(chemin, langue)
        except Exception as erreur:
            print(f"[Audio] Échec de transcription ({langue}) : {erreur}")
        return None


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
