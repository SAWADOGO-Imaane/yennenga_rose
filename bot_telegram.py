"""
Bot Telegram Yennenga Rose.

Lancer :  python bot_telegram.py
Le token se met dans le fichier .env (TELEGRAM_TOKEN=...).
"""
import asyncio
import logging
from datetime import timedelta
from pathlib import Path

from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler, PicklePersistence, filters,
)

import config
from audio import Transcripteur, fichier_audio, synthese_fr
from centres import Centres
from moteur import CLAVIER_MENU, Moteur, Reponse
from rag import RAG
from textes import texte

logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("yennenga")

moteur = Moteur(RAG(), Centres())
transcripteur = Transcripteur()

LIMITE_LEGENDE = 1000  # Telegram limite la légende d'un audio à 1024 caractères


# ---------------------------------------------------------------
# Affichage des réponses du moteur
# ---------------------------------------------------------------
def clavier(boutons):
    if not boutons:
        return None
    lignes = [boutons[i:i + 3] for i in range(0, len(boutons), 3)]
    return ReplyKeyboardMarkup(lignes, resize_keyboard=True)


async def envoyer_fichier_audio(bot, chat_id, chemin: Path, legende=None, markup=None):
    with open(chemin, "rb") as f:
        if chemin.suffix in (".ogg", ".opus"):
            await bot.send_voice(chat_id, f, caption=legende, reply_markup=markup)
        else:
            await bot.send_audio(chat_id, f, caption=legende, reply_markup=markup)


async def envoyer(bot, chat_id, reponses: list[Reponse], langue: str):
    for i, r in enumerate(reponses):
        dernier = i == len(reponses) - 1
        # Le clavier du dernier message qui en définit un reste affiché
        markup = clavier(r.clavier) if r.clavier else None

        audio = fichier_audio(r.cle, langue) if r.cle else None
        if audio and len(r.texte) <= LIMITE_LEGENDE:
            await envoyer_fichier_audio(bot, chat_id, audio, r.texte, markup)
        else:
            if audio:
                await envoyer_fichier_audio(bot, chat_id, audio)
            await bot.send_message(chat_id, r.texte, reply_markup=markup)

        # Réponse libre en français : version audio générée (si activée)
        if r.lire_a_voix_haute and langue == "fr":
            mp3 = await asyncio.to_thread(synthese_fr, r.texte)
            if mp3:
                await envoyer_fichier_audio(bot, chat_id, mp3)
                mp3.unlink(missing_ok=True)

        if not dernier:
            await asyncio.sleep(0.4)  # garde l'ordre et laisse le temps d'écouter


# ---------------------------------------------------------------
# Rappels mensuels
# ---------------------------------------------------------------
async def envoyer_rappel(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    langue = job.data.get("langue", "fr")
    etat = context.application.user_data.get(job.chat_id)
    if etat is not None and "mode" in etat:
        etat["mode"] = "menu"  # pour que "1" ouvre bien l'auto-palpation
    rappel = Reponse(texte("rappel_message", langue), cle="rappel_message", clavier=CLAVIER_MENU)
    await envoyer(context.bot, job.chat_id, [rappel], langue)


def programmer_rappel(job_queue, chat_id: int, langue: str, premier=None):
    annuler_rappel(job_queue, chat_id)
    intervalle = timedelta(days=config.INTERVALLE_RAPPEL_JOURS)
    job_queue.run_repeating(
        envoyer_rappel, interval=intervalle, first=premier or intervalle,
        chat_id=chat_id, name=f"rappel-{chat_id}", data={"langue": langue},
    )


def annuler_rappel(job_queue, chat_id: int):
    for job in job_queue.get_jobs_by_name(f"rappel-{chat_id}"):
        job.schedule_removal()


async def appliquer_actions(context, chat_id, etat, reponses):
    for r in reponses:
        if r.action == "rappel_on":
            programmer_rappel(context.job_queue, chat_id, etat.get("langue", "fr"))
        elif r.action == "rappel_off":
            annuler_rappel(context.job_queue, chat_id)


# ---------------------------------------------------------------
# Gestionnaires Telegram
# ---------------------------------------------------------------
async def traiter_et_repondre(update: Update, context, message: str, vocal_langue=None):
    etat = context.user_data
    chat_id = update.effective_chat.id
    reponses = await asyncio.to_thread(moteur.traiter, etat, message, vocal_langue)
    await appliquer_actions(context, chat_id, etat, reponses)
    await envoyer(context.bot, chat_id, reponses, etat.get("langue", "fr"))


async def cmd_start(update: Update, context):
    await traiter_et_repondre(update, context, "/start")


async def cmd_menu(update: Update, context):
    await traiter_et_repondre(update, context, "menu")


async def cmd_langue(update: Update, context):
    context.user_data["mode"] = "menu"
    await traiter_et_repondre(update, context, "7")


async def cmd_rappel_test(update: Update, context):
    """Pour la démo devant le jury : un rappel arrive dans 20 secondes."""
    chat_id = update.effective_chat.id
    context.job_queue.run_once(
        envoyer_rappel, when=20, chat_id=chat_id,
        data={"langue": context.user_data.get("langue", "fr")},
    )
    await update.message.reply_text("⏱️ Rappel de test programmé dans 20 secondes.")


async def message_texte(update: Update, context):
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    await traiter_et_repondre(update, context, update.message.text)


async def message_vocal(update: Update, context):
    etat = context.user_data
    chat_id = update.effective_chat.id
    if "langue" not in etat:  # pas encore de langue choisie : on montre l'accueil
        await traiter_et_repondre(update, context, "/start")
        return

    langue = etat["langue"]
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    vocal = update.message.voice or update.message.audio
    fichier = await vocal.get_file()
    chemin = config.DOSSIER_TMP / f"vocal_{chat_id}_{vocal.file_unique_id}.ogg"
    await fichier.download_to_drive(chemin)

    try:
        texte_transcrit = await asyncio.to_thread(transcripteur.transcrire, chemin, langue)
    finally:
        chemin.unlink(missing_ok=True)

    if not texte_transcrit:
        cle = "vocal_langue_locale" if langue in ("mos", "dyu") else "pas_compris_vocal"
        await envoyer(context.bot, chat_id, [Reponse(texte(cle, langue), cle=cle)], langue)
        if etat.get("mode") != "questionnaire":
            await traiter_et_repondre(update, context, "menu")
        return

    await context.bot.send_message(chat_id, f"📝 J'ai entendu : « {texte_transcrit} »")
    await traiter_et_repondre(update, context, texte_transcrit, vocal_langue=langue)


async def autre_message(update: Update, context):
    await traiter_et_repondre(update, context, "menu")


async def erreur(update, context):
    log.exception("Erreur pendant le traitement", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        await context.bot.send_message(
            update.effective_chat.id,
            "Désolée, un problème est survenu. Tapez 0 pour revenir au menu.",
        )


async def apres_demarrage(application: Application):
    """Reprogramme les rappels des utilisatrices après un redémarrage du bot."""
    nb = 0
    for user_id, etat in application.user_data.items():
        if etat.get("rappel"):
            programmer_rappel(application.job_queue, user_id, etat.get("langue", "fr"))
            nb += 1
    log.info("Bot démarré. %d rappel(s) reprogrammé(s).", nb)


def main():
    if not config.TELEGRAM_TOKEN:
        raise SystemExit("❌ TELEGRAM_TOKEN manquant dans le fichier .env")

    persistance = PicklePersistence(filepath=config.RACINE / "data" / "etat_bot.pickle")
    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .persistence(persistance)
        .post_init(apres_demarrage)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("langue", cmd_langue))
    app.add_handler(CommandHandler("rappel_test", cmd_rappel_test))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, message_vocal))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_texte))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, autre_message))
    app.add_error_handler(erreur)

    log.info("Yennenga Rose démarre… (Ctrl+C pour arrêter)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
