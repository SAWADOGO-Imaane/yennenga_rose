"""Configuration centrale, lue depuis le fichier .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

RACINE = Path(__file__).resolve().parent
load_dotenv(RACINE / ".env")

# --- Telegram ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")

# --- WhatsApp (Twilio) ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
# Adresse publique du serveur (donnée par ngrok), ex. https://abcd-1234.ngrok-free.app
PUBLIC_URL = os.getenv("PUBLIC_URL", "")

# --- LLM (API compatible OpenAI : Groq, OpenAI, Mistral, Ollama...) ---
# Si LLM_API_KEY est vide, le bot répond avec le passage le plus pertinent
# des documents (mode extractif), sans appeler d'IA.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

# --- Transcription audio ---
# "whisper" pour le français (léger, fiable)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
# MMS pour le mooré / dioula : lourd (~4 Go), expérimental. Mettre 1 pour activer.
ACTIVER_MMS = os.getenv("ACTIVER_MMS", "0") == "1"
MMS_MODEL = os.getenv("MMS_MODEL", "facebook/mms-1b-all")

# --- Synthèse vocale des réponses libres en français (gTTS, nécessite internet) ---
ACTIVER_TTS_FR = os.getenv("ACTIVER_TTS_FR", "0") == "1"

# --- Chemins ---
DOSSIER_AUDIOS = RACINE / "audios"
DOSSIER_DOCS = RACINE / "data" / "docs"
FICHIER_CENTRES = RACINE / "data" / "centres.json"
DOSSIER_TMP = RACINE / "tmp"
DOSSIER_TMP.mkdir(exist_ok=True)

# Intervalle des rappels d'auto-examen (en jours)
INTERVALLE_RAPPEL_JOURS = int(os.getenv("INTERVALLE_RAPPEL_JOURS", "30"))
