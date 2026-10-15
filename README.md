# 🎗️ Yennenga Rose

Assistante d'information et d'orientation sur le cancer du sein, sur Telegram et WhatsApp,
en **mooré, dioula et français**, pensée pour les femmes qui ne lisent pas.
Hackathon Octobre Rose 2026 — Orange Digital Center Ouagadougou.

> Yennenga Rose **ne pose aucun diagnostic**. Elle informe, apprend l'auto-examen,
> aide à savoir quand consulter et indique où aller.

## Fonctionnalités

| Menu | Fonction | Comment |
|---|---|---|
| 1 🖐️ | Apprendre l'auto-palpation | Audio enregistré + texte |
| 2 🩺 | Questionnaire d'orientation | Questions audio, réponses 1/2 ou vocal (oui/non, ẽẽ/ayo, ɔwɔ/ayi) |
| 3 ⚠️ | Signes d'alerte | Audio enregistré + texte |
| 4 📍 | Centres de santé par ville | `data/centres.json` |
| 5 ❓ | Question libre écrite ou vocale | Whisper (vocal fr) → RAG → réponse (+ voix si activée) |
| 6 🔔 | Rappel mensuel d'auto-examen | Planification Telegram |
| 7 🌐 | Changer de langue | |

Navigation **par chiffres** (boutons ou chiffre dit dans un vocal : « deux », « yiibu », « fila »),
pour que tout le parcours soit utilisable sans savoir lire.

## Structure

```
octobre-rose-bot/
├── bot_telegram.py        # le bot Telegram (point d'entrée)
├── bot_whatsapp.py        # le bot WhatsApp via Twilio (point d'entrée)
├── demo_web.py            # démo web de secours (plan B pour le jury)
├── moteur.py              # logique de conversation (commune aux deux)
├── questionnaire.py       # questions et règle d'orientation
├── textes.py              # TOUS les messages (à faire relire par la médecin)
├── rag.py                 # réponses aux questions libres
├── audio.py               # audios enregistrés, transcription, synthèse vocale
├── centres.py             # recherche des centres par ville
├── verifier_audios.py     # fiche des messages à enregistrer + bilan
├── data/
│   ├── centres.json       # liste des centres (À VÉRIFIER)
│   └── docs/              # base de connaissances du RAG (.md / .txt)
├── audios/
│   ├── commun/choix_langue.ogg
│   ├── mos/<clé>.ogg      # mooré
│   ├── dyu/<clé>.ogg      # dioula
│   └── fr/<clé>.ogg       # français (optionnel)
└── tests/test_moteur.py
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # puis remplir TELEGRAM_TOKEN
```

Installer aussi **ffmpeg** (nécessaire pour les vocaux) :
- Ubuntu : `sudo apt install ffmpeg`
- Windows : `winget install ffmpeg`

### Créer le bot Telegram
1. Sur Telegram, ouvrir **@BotFather** → `/newbot`.
2. Donner un nom (ex. *Yennenga Rose*) et un identifiant finissant par `bot`.
3. Copier le token dans `.env` : `TELEGRAM_TOKEN=...`
4. Optionnel : `/setcommands` →
   ```
   start - Commencer
   menu - Revenir au menu
   langue - Changer de langue
   ```

## Lancer

```bash
python -m pytest -q        # vérifier que tout marche (14 tests)
python bot_telegram.py     # le bot
python demo_web.py         # la démo web → http://127.0.0.1:7860
```

## Ajouter les audios (mooré, dioula)

```bash
python verifier_audios.py
```
Génère `TEXTES_A_ENREGISTRER.md` : chaque message, avec le nom exact du fichier à créer.
Les locutrices enregistrent un vocal WhatsApp/Telegram, on le renomme
(ex. `audios/mos/autopalpation.ogg`) et le bot l'envoie automatiquement.
Relancer le script pour voir ce qui manque.

## WhatsApp (Twilio + ngrok)

Trois fenêtres d'invite de commandes, environnement activé dans chacune :
```cmd
python bot_telegram.py
python bot_whatsapp.py
ngrok http 8000
```
Dans la console Twilio (Messaging → Try it out → Send a WhatsApp message → Sandbox settings),
mettre `https://<adresse-ngrok>/whatsapp` dans « When a message comes in » (POST).
Chaque testeuse envoie d'abord `join <code>` au numéro du sandbox.
Limite : pas de boutons (choix écrits en clair) et pas de rappels mensuels sur WhatsApp
(WhatsApp interdit d'écrire en premier sans modèle de message validé).

## Options

- **IA (LLM)** : avec `LLM_API_KEY` (ex. Groq, gratuit), les réponses libres sont reformulées
  simplement, uniquement à partir des documents. Sans clé, le bot renvoie le passage le plus pertinent.
- **Voix des réponses en français** : `ACTIVER_TTS_FR=1`.
- **Vocaux en mooré / dioula** : `ACTIVER_MMS=1` + décommenter torch/transformers/soundfile.
  Modèle MMS de Meta, expérimental : fiable pour les chiffres et oui/non, pas pour des questions médicales libres.
- **Démo du rappel devant le jury** : commande `/rappel_test` (rappel en 20 secondes).

## À faire avant la démo

- [ ] Faire relire `textes.py`, `questionnaire.py` et `data/docs/` par la médecin
- [ ] Vérifier `data/centres.json` (noms, services ; ajouter numéros confirmés)
- [ ] Enregistrer au moins les messages ⭐ prioritaires en mooré (+ accueil en dioula)
- [ ] Vérifier les mots oui/non et les chiffres en mooré/dioula (`questionnaire.py`, `moteur.py`)
- [ ] Enregistrer une vidéo de la démo (plan B si pas d'internet)
