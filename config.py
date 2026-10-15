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
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+17372508034")
# Adresse publique du serveur (donnée par ngrok), ex. https://abcd-1234.ngrok-free.app
PUBLIC_URL = os.getenv("PUBLIC_URL", "")

# --- WhatsApp (API Cloud de Meta) ---
META_TOKEN = os.getenv("META_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")

# --- LLM (API compatible OpenAI : Groq, OpenAI, Mistral, Ollama...) ---
# Si LLM_API_KEY est vide, le bot répond avec le passage le plus pertinent
# des documents (mode extractif), sans appeler d'IA.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
# Modèle qui « voit » les images (analyse visuelle d'orientation de l'app)
VISION_MODEL = os.getenv("VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
# Par défaut la vision utilise la même clé que Groq. Pour un autre fournisseur
# (ex. Google Gemini, gratuit), remplir ces deux lignes dans .env :
VISION_API_KEY = os.getenv("VISION_API_KEY", "") or LLM_API_KEY
VISION_BASE_URL = os.getenv("VISION_BASE_URL", "") or LLM_BASE_URL

# --- Transcription audio ---
# "whisper" pour le français (léger, fiable)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
# "groq" = Whisper sur les serveurs de Groq (rapide, utilise LLM_API_KEY) ; "local" = sur le PC
TRANSCRIPTION = os.getenv("TRANSCRIPTION", "groq")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
# Groq récupère le vocal directement chez Twilio (plus rapide). 0 = le PC télécharge le vocal.
GROQ_PAR_URL = os.getenv("GROQ_PAR_URL", "1") == "1"
# MMS pour le mooré / dioula : lourd (~4 Go), expérimental. Mettre 1 pour activer.
ACTIVER_MMS = os.getenv("ACTIVER_MMS", "0") == "1"
MMS_MODEL = os.getenv("MMS_MODEL", "facebook/mms-1b-all")

# --- Synthèse vocale des réponses libres en français (gTTS, nécessite internet) ---
ACTIVER_TTS_FR = os.getenv("ACTIVER_TTS_FR", "0") == "1"

# --- Répondre par un vocal quand on reçoit un vocal (français, gTTS, nécessite internet) ---
REPONSE_VOCALE = os.getenv("REPONSE_VOCALE", "1") == "1"
VOIX_EDGE = os.getenv("VOIX_EDGE", "fr-FR-DeniseNeural")
# Twilio abandonne après 15 s : on vise une réponse en moins de 13 s
BUDGET_REPONSE_S = float(os.getenv("BUDGET_REPONSE_S", "14"))

# --- Chemins ---
DOSSIER_AUDIOS = RACINE / "audios"
DOSSIER_DOCS = RACINE / "data" / "docs"
FICHIER_CENTRES = RACINE / "data" / "centres.json"
DOSSIER_TMP = RACINE / "tmp"
DOSSIER_TMP.mkdir(exist_ok=True)

# Intervalle des rappels d'auto-examen (en jours)
INTERVALLE_RAPPEL_JOURS = int(os.getenv("INTERVALLE_RAPPEL_JOURS", "30"))
