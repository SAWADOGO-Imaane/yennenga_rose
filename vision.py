"""
Analyse visuelle d'ORIENTATION (expérimentale) — photo ou courte vidéo du sein.

⚠️ Ce n'est PAS un diagnostic. Le modèle ne dit jamais « cancer » ou « pas cancer » :
il repère seulement des signes VISIBLES qui doivent faire consulter
(les mêmes que le questionnaire : peau rouge / peau d'orange, mamelon rentré,
plaie, changement de forme, écoulement). Une boule ne se voit pas toujours :
une image « sans signe visible » ne rassure jamais à elle seule.

Confidentialité : l'image est envoyée au modèle, puis SUPPRIMÉE du serveur.
Rien n'est enregistré.

Modèle : un modèle de vision (VISION_MODEL dans .env), sur Groq ou un autre fournisseur compatible OpenAI.
"""
import base64
import json
import subprocess
import uuid
from pathlib import Path

import config

# Signes visibles -> question correspondante du questionnaire
SIGNES = {
    "rougeur": ("peau rouge", "peau"),
    "peau_orange": ("peau qui ressemble à une peau d'orange", "peau"),
    "mamelon_rentre": ("mamelon rentré vers l'intérieur", "mamelon"),
    "plaie": ("plaie ou croûte sur le sein ou le mamelon", "plaie"),
    "deformation": ("changement de forme ou de taille d'un sein", "forme"),
    "gonflement": ("gonflement d'une partie du sein ou de l'aisselle", "forme"),
    "ecoulement": ("liquide qui sort du mamelon", "ecoulement"),
}

PROMPT_VISION = """Tu aides des agents de santé au Burkina Faso à ORIENTER des femmes (pas à diagnostiquer).
On te montre une ou plusieurs images de la poitrine d'une femme, prises par elle-même avec un téléphone.

Observe UNIQUEMENT ce qui est visible et réponds avec ce JSON, sans rien d'autre :
{
  "image_utilisable": true ou false,
  "raison": "si inutilisable : floue / trop sombre / trop loin / ce n'est pas la poitrine",
  "signes": {
    "rougeur": true ou false,
    "peau_orange": true ou false,
    "mamelon_rentre": true ou false,
    "plaie": true ou false,
    "deformation": true ou false,
    "gonflement": true ou false,
    "ecoulement": true ou false
  },
  "description": "1 ou 2 phrases très simples sur ce que tu vois, sans aucun mot de diagnostic"
}

Règles :
- Ne dis JAMAIS « cancer », « tumeur », « bénin », « malin » ou « normal ».
- En cas de doute sur un signe, mets true (mieux vaut consulter pour rien que rater un signe).
- Si l'image ne montre pas clairement la poitrine, mets "image_utilisable": false."""


# ---------------------------------------------------------------
# Préparation des images
# ---------------------------------------------------------------
def reduire_image(chemin: Path) -> Path:
    """Photo de téléphone (souvent > 4 Mo) -> JPEG 1024 px maximum."""
    sortie = config.DOSSIER_TMP / f"img_{uuid.uuid4().hex}.jpg"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(chemin),
         "-vf", "scale='min(1024,iw)':'min(1024,ih)':force_original_aspect_ratio=decrease",
         "-frames:v", "1", "-q:v", "4", str(sortie)],
        check=True, timeout=30,
    )
    return sortie


def images_de_la_video(chemin: Path, nombre: int = 3) -> list[Path]:
    """Prend `nombre` images réparties dans la vidéo (à 25 %, 50 %, 75 %)."""
    duree = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(chemin)],
        capture_output=True, text=True, check=True, timeout=20,
    ).stdout.strip() or 0)
    images = []
    for i in range(1, nombre + 1):
        moment = duree * i / (nombre + 1)
        sortie = config.DOSSIER_TMP / f"vid_{uuid.uuid4().hex}.jpg"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{moment:.2f}", "-i", str(chemin),
             "-vf", "scale='min(1024,iw)':'min(1024,ih)':force_original_aspect_ratio=decrease",
             "-frames:v", "1", "-q:v", "4", str(sortie)],
            check=True, timeout=30,
        )
        if sortie.exists() and sortie.stat().st_size > 0:
            images.append(sortie)
    return images


def en_data_url(chemin: Path) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(chemin.read_bytes()).decode()


# ---------------------------------------------------------------
# Appel du modèle de vision
# ---------------------------------------------------------------
def analyser_images(images: list[Path]) -> dict:
    """Renvoie le JSON du modèle (voir PROMPT_VISION). Lève une exception si impossible."""
    if not config.VISION_API_KEY:
        raise RuntimeError("clé manquante dans .env (VISION_API_KEY ou LLM_API_KEY)")
    from openai import OpenAI

    client = OpenAI(api_key=config.VISION_API_KEY, base_url=config.VISION_BASE_URL, timeout=60)
    contenu = [{"type": "text", "text": "Voici les images. Réponds avec le JSON demandé."}]
    contenu += [{"type": "image_url", "image_url": {"url": en_data_url(i)}} for i in images[:3]]
    base = dict(
        model=config.VISION_MODEL,
        messages=[{"role": "system", "content": PROMPT_VISION}, {"role": "user", "content": contenu}],
        temperature=0,
        max_tokens=3000,  # les modèles qui « réfléchissent » consomment des jetons avant le JSON
    )
    # On essaie du plus strict au plus simple : chaque fournisseur accepte des options différentes
    essais = [
        {"response_format": {"type": "json_object"}, "extra_body": {"reasoning_effort": "none"}},
        {"response_format": {"type": "json_object"}},
        {},
    ]
    derniere_erreur = None
    for options in essais:
        try:
            reponse = client.chat.completions.create(**base, **options)
            return lire_json(reponse.choices[0].message.content or "")
        except Exception as erreur:
            texte = str(erreur)
            if "model_not_found" in texte or "does not exist" in texte:
                raise
            print(f"[Vision] Essai sans succès ({list(options) or 'simple'}) : {texte[:200]}")
            derniere_erreur = erreur
    raise derniere_erreur


def lire_json(texte: str) -> dict:
    """Extrait le JSON même s'il est entouré de ```json ... ``` ou de texte."""
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin == -1:
        raise ValueError(f"réponse sans JSON : {texte[:200]}")
    return json.loads(texte[debut:fin + 1])


# ---------------------------------------------------------------
# Décision (faite par NOTRE code, pas par l'IA)
# ---------------------------------------------------------------
def orientation(analyse: dict) -> dict:
    """Transforme la réponse du modèle en orientation simple et prudente.

    issue = "reprendre"  : image inutilisable
            "consulter"  : au moins un signe visible
            "aucun_signe": rien de visible (=> jamais rassurant à lui seul)
    """
    if not analyse.get("image_utilisable", False):
        return {"issue": "reprendre", "signes": [], "questions": [],
                "raison": analyse.get("raison", "")}
    signes = analyse.get("signes") or {}
    trouves = [cle for cle in SIGNES if signes.get(cle) is True]
    return {
        "issue": "consulter" if trouves else "aucun_signe",
        "signes": [SIGNES[c][0] for c in trouves],
        "questions": sorted({SIGNES[c][1] for c in trouves}),
        "description": analyse.get("description", ""),
    }


def message_orientation(o: dict) -> str:
    if o["issue"] == "reprendre":
        raison = f" ({o['raison']})" if o.get("raison") else ""
        return ("📷 Je n'arrive pas à bien voir l'image" + raison + ". Reprenez la photo à la lumière "
                "du jour, de face, à environ 50 cm. Vous pouvez aussi répondre au questionnaire.")
    if o["issue"] == "consulter":
        liste = "\n".join(f"• {s}" for s in o["signes"])
        return ("👩‍⚕️ Sur l'image, je remarque peut-être :\n" + liste + "\n\n"
                "Ce n'est PAS un diagnostic : beaucoup de ces signes ont d'autres causes. "
                "Mais ils doivent être examinés par un agent de santé, rapidement, dans les prochains jours.")
    return ("🌼 Je ne vois pas de signe d'alerte sur l'image. Attention : une boule ne se voit pas "
            "toujours sur une photo. Touchez aussi vos seins (choix 1), répondez au questionnaire "
            "(choix 2), et faites-vous examiner par un agent de santé si quelque chose a changé.")
