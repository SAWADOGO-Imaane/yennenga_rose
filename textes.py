"""
Tous les messages du bot.

Chaque message a une CLÉ. Cette clé sert aussi à retrouver l'audio enregistré :
    audios/<langue>/<clé>.ogg   (ou .mp3 / .m4a / .opus)
Langues : "mos" (mooré), "dyu" (dioula), "fr" (français).

Pour le mooré et le dioula, le bot envoie l'AUDIO enregistré par une locutrice.
Le texte français est affiché en dessous (utile si un proche sait lire).
Si l'équipe écrit aussi une traduction, l'ajouter dans TRADUCTIONS ci-dessous.

⚠️ Tous les messages médicaux doivent être relus par la médecin.
"""

LANGUES = {"mos": "Mooré", "dyu": "Dioula", "fr": "Français"}

TEXTES = {
    # ---------- Accueil ----------
    # Audio spécial : audios/commun/choix_langue.ogg (les 3 langues à la suite)
    "choix_langue": (
        "Bonjour 🌸 Je suis Yennenga Rose, votre assistante pour la santé des seins.\n"
        "Choisissez votre langue :\n"
        "1 = Mooré    2 = Dioula    3 = Français"
    ),
    "bienvenue": (
        "Bienvenue 🌸 Ici, vous pouvez apprendre à prendre soin de vos seins, "
        "en toute discrétion. Je ne suis pas médecin : je vous informe et je vous "
        "aide à savoir quand consulter."
    ),
    "menu": (
        "Que voulez-vous faire ? Appuyez sur un chiffre :\n"
        "1 🖐️ Apprendre à examiner mes seins\n"
        "2 🩺 J'ai remarqué quelque chose d'anormal\n"
        "3 ⚠️ Les signes qui doivent alerter\n"
        "4 📍 Où me faire examiner\n"
        "5 ❓ Poser une question (écrite ou vocale)\n"
        "6 🔔 Recevoir un rappel chaque mois\n"
        "7 🌐 Changer de langue"
    ),
    "choix_invalide": "Je n'ai pas compris. Appuyez sur un des chiffres proposés.",

    # ---------- Auto-palpation ----------
    "autopalpation": (
        "🖐️ Comment examiner vos seins, une fois par mois :\n\n"
        "Quand ? Quelques jours après la fin des règles. Si vous n'avez plus de règles, "
        "choisissez une date fixe chaque mois.\n\n"
        "1. Regardez : debout devant un miroir, bras le long du corps puis levés. "
        "Cherchez un changement de forme, de taille, de peau ou du mamelon.\n"
        "2. Touchez : avec le plat de trois doigts, faites de petits cercles en appuyant "
        "doucement puis plus fort, sur tout le sein.\n"
        "3. N'oubliez pas l'aisselle : des boules peuvent aussi apparaître sous le bras.\n"
        "4. Pressez doucement le mamelon : regardez s'il sort un liquide.\n"
        "5. Recommencez couchée sur le dos, un bras derrière la tête.\n\n"
        "Si vous remarquez quelque chose de nouveau, choisissez 2 dans le menu."
    ),

    # ---------- Signes d'alerte ----------
    "signes_alerte": (
        "⚠️ Consultez rapidement si vous remarquez :\n"
        "• une boule ou une zone dure dans le sein ou sous l'aisselle\n"
        "• une peau rouge, creusée ou qui ressemble à une peau d'orange\n"
        "• un liquide qui sort du mamelon (autre que le lait)\n"
        "• un mamelon qui rentre vers l'intérieur\n"
        "• un changement de forme ou de taille d'un sein\n"
        "• une plaie du sein qui ne guérit pas\n\n"
        "Ces signes ne veulent pas toujours dire cancer. Mais seul un agent de santé "
        "peut le vérifier. Plus on consulte tôt, mieux on soigne."
    ),

    # ---------- Questionnaire ----------
    "questionnaire_intro": (
        "Je vais vous poser quelques questions. Ce n'est pas un diagnostic : "
        "c'est pour vous aider à savoir si vous devez consulter.\n"
        "Répondez 1 pour OUI, 2 pour NON."
    ),
    "q_boule": "Avez-vous senti une boule ou une zone dure dans un sein ou sous l'aisselle ?",
    "q_peau": "La peau du sein est-elle rouge, creusée ou ressemble-t-elle à une peau d'orange ?",
    "q_ecoulement": "Un liquide sort-il du mamelon, alors que vous n'allaitez pas ?",
    "q_mamelon": "Votre mamelon s'est-il récemment rentré vers l'intérieur ?",
    "q_forme": "Avez-vous remarqué un changement de forme ou de taille d'un sein ?",
    "q_plaie": "Avez-vous une plaie sur le sein ou le mamelon qui ne guérit pas ?",
    "q_douleur": "Avez-vous une douleur dans un seul sein depuis plus de deux semaines ?",
    "q_famille": "Votre mère, votre sœur ou votre fille a-t-elle eu un cancer du sein ?",
    "q_age": "Avez-vous 35 ans ou plus ?",
    "q_antecedent": "Avez-vous déjà eu une maladie ou une opération du sein ?",
    "reponse_oui_non": "Répondez 1 pour OUI ou 2 pour NON.",

    "resultat_consulter": (
        "👩‍⚕️ Vous avez signalé un signe qui doit être examiné par un agent de santé.\n"
        "Cela ne veut pas forcément dire que c'est un cancer : beaucoup de ces signes "
        "ont d'autres causes. Mais il est important de consulter rapidement, "
        "dans les prochains jours. N'ayez pas peur : découvert tôt, un petit cancer du sein "
        "se soigne très bien (95 femmes sur 100 sont en vie 5 ans après)."
    ),
    "resultat_depistage": (
        "🌷 Vous n'avez pas signalé de signe d'alerte. Vous avez cependant un ou "
        "plusieurs facteurs de risque. Parlez du dépistage à un agent de santé lors "
        "de votre prochaine visite : il doit examiner vos seins, même si vous venez pour autre chose. "
        "À partir de 45 ans environ, une mammographie est conseillée tous les deux ans. "
        "Continuez aussi à examiner vos seins chaque mois."
    ),
    "resultat_surveillance": (
        "🌼 Vous n'avez pas signalé de signe d'alerte aujourd'hui. Continuez à examiner "
        "vos seins chaque mois. Si quelque chose change, consultez."
    ),

    # ---------- Centres ----------
    "demande_ville": "📍 Dans quelle ville êtes-vous ? Appuyez sur le chiffre :",
    "centres_intro": "Voici des structures où vous pouvez vous rendre (service de gynécologie) :",
    "centres_autre": (
        "Rendez-vous au CSPS ou au CMA le plus proche de chez vous. "
        "L'agent de santé vous examinera et vous orientera si besoin."
    ),

    # ---------- Question libre ----------
    "question_intro": (
        "❓ Posez votre question, en écrivant ou en envoyant un message vocal.\n"
        "Tapez 0 pour revenir au menu."
    ),
    "question_suite": "Vous pouvez poser une autre question, ou taper 0 pour le menu.",
    "question_inconnue": (
        "Je n'ai pas d'information fiable pour répondre à cette question. "
        "Parlez-en à un agent de santé : il saura vous répondre."
    ),
    "rappel_symptome": (
        "👉 Si vous avez remarqué un de ces signes, tapez 0 puis 2 pour répondre à quelques "
        "questions et savoir où consulter."
    ),
    "pas_compris_vocal": (
        "Je n'ai pas bien compris votre message vocal. Utilisez le menu avec les "
        "chiffres, ou parlez-en à un agent de santé."
    ),
    "vocal_langue_locale": (
        "La compréhension des vocaux en mooré et en dioula est encore en apprentissage. "
        "Pour être sûre d'avoir la bonne information, utilisez le menu avec les chiffres."
    ),
    "ecoute": "🎧 J'écoute votre message…",

    # ---------- Rappels ----------
    "rappel_active": (
        "🔔 C'est noté ! Je vous enverrai un petit rappel chaque mois pour examiner "
        "vos seins. Pour l'arrêter, choisissez 6 à nouveau."
    ),
    "rappel_desactive": "🔕 Les rappels sont arrêtés.",
    "rappel_message": (
        "🌸 Bonjour ! C'est le moment de votre examen des seins du mois. "
        "Cela prend 5 minutes. Tapez 1 si vous voulez revoir comment faire."
    ),

    "retour_menu": "Tapez 0 pour revenir au menu.",

    # Ajouté automatiquement aux centres pendant le mois d'octobre
    "info_octobre": (
        "🎗️ Octobre Rose : des campagnes de dépistage GRATUIT (échographie, mammographie, examen des seins) "
        "sont organisées dans les hôpitaux, les CSPS et par des cliniques mobiles, jusque dans les villages. "
        "Demandez à votre centre de santé où et quand a lieu la prochaine."
    ),
}

# Traductions écrites optionnelles : TRADUCTIONS["mos"]["menu"] = "..."
TRADUCTIONS = {"mos": {}, "dyu": {}}


def texte(cle: str, langue: str = "fr") -> str:
    """Texte à afficher : traduction écrite si elle existe, sinon le français."""
    return TRADUCTIONS.get(langue, {}).get(cle) or TEXTES[cle]
