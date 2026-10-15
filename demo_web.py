"""
Démo web de secours (plan B si Telegram ou internet pose problème devant le jury).
Même moteur que le bot Telegram, dans le navigateur, avec micro et audios.

Lancer :  python demo_web.py   puis ouvrir http://127.0.0.1:7860
"""
import shutil
import uuid

import gradio as gr

import config
from audio import Transcripteur, fichier_audio, synthese_fr
from centres import Centres
from moteur import Moteur
from rag import RAG

moteur = Moteur(RAG(), Centres())
transcripteur = Transcripteur()


def rendre(reponses, etat):
    """Transforme les réponses du moteur en messages Gradio (audio + texte)."""
    langue = etat.get("langue", "fr")
    messages = []
    for r in reponses:
        audio = fichier_audio(r.cle, langue) if r.cle else None
        if audio:
            messages.append({"role": "assistant", "content": {"path": str(audio)}})
        messages.append({"role": "assistant", "content": r.texte})
        if r.lire_a_voix_haute and langue == "fr":
            mp3 = synthese_fr(r.texte)
            if mp3:
                messages.append({"role": "assistant", "content": {"path": str(mp3)}})
        if r.action == "rappel_on":
            messages.append({"role": "assistant", "content": "(Démo web : les rappels fonctionnent sur Telegram.)"})
    return messages


def demarrer(etat):
    etat = {}
    return rendre(moteur.traiter(etat, "/start"), etat), etat


def envoyer_texte(message, historique, etat):
    if not message or not message.strip():
        return "", historique, etat
    historique = historique + [{"role": "user", "content": message}]
    historique += rendre(moteur.traiter(etat, message), etat)
    return "", historique, etat


def envoyer_vocal(chemin, historique, etat):
    if not chemin:
        return None, historique, etat
    langue = etat.get("langue", "fr")
    copie = config.DOSSIER_TMP / f"web_{uuid.uuid4().hex}.wav"
    shutil.copy(chemin, copie)
    historique = historique + [{"role": "user", "content": {"path": str(copie)}}]

    texte = transcripteur.transcrire(copie, langue)
    if not texte:
        cle = "vocal_langue_locale" if langue in ("mos", "dyu") else "pas_compris_vocal"
        from moteur import Reponse
        from textes import texte as t
        historique += rendre([Reponse(t(cle, langue), cle=cle)], etat)
        return None, historique, etat

    historique.append({"role": "assistant", "content": f"📝 J'ai entendu : « {texte} »"})
    historique += rendre(moteur.traiter(etat, texte, vocal_langue=langue), etat)
    return None, historique, etat


with gr.Blocks(title="Yennenga Rose", theme=gr.themes.Soft(primary_hue="pink")) as demo:
    gr.Markdown("# 🎗️ Yennenga Rose\nAssistante d'information et d'orientation sur le cancer du sein — "
                "mooré, dioula, français. *Ne remplace pas un avis médical.*")
    etat = gr.State({})
    try:
        chat = gr.Chatbot(type="messages", height=520, label="Conversation")
    except TypeError:  # Gradio 6 : format "messages" par défaut
        chat = gr.Chatbot(height=520, label="Conversation")
    with gr.Row():
        saisie = gr.Textbox(placeholder="Tapez un chiffre ou votre question…", scale=4, show_label=False)
        bouton = gr.Button("Envoyer", variant="primary", scale=1)
    micro = gr.Audio(sources=["microphone"], type="filepath", label="🎤 Message vocal")
    recommencer = gr.Button("🔄 Recommencer")

    demo.load(demarrer, [etat], [chat, etat])
    saisie.submit(envoyer_texte, [saisie, chat, etat], [saisie, chat, etat])
    bouton.click(envoyer_texte, [saisie, chat, etat], [saisie, chat, etat])
    micro.stop_recording(envoyer_vocal, [micro, chat, etat], [micro, chat, etat])
    recommencer.click(demarrer, [etat], [chat, etat])

if __name__ == "__main__":
    demo.launch(allowed_paths=[str(config.DOSSIER_AUDIOS), str(config.DOSSIER_TMP)])
