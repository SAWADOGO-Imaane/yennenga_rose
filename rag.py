"""
RAG léger pour les questions libres.

1. Les documents de data/docs/ (.md ou .txt) sont découpés en passages.
2. Recherche des passages les plus proches de la question (TF-IDF, sans GPU).
3. Si une clé LLM est configurée : l'IA reformule une réponse simple à partir
   de ces passages UNIQUEMENT. Sinon : on renvoie directement le meilleur passage.

Pour ajouter des connaissances : déposer un fichier .md ou .txt dans data/docs/
(sources fiables : OMS, ministère de la Santé, relu par la médecin).
"""
import re
import unicodedata
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import config

SEUIL_PERTINENCE = 0.08
NB_PASSAGES = 3

PROMPT_SYSTEME = """Tu es Yennenga Rose, une assistante d'information sur le cancer du sein au Burkina Faso.
Règles strictes :
- Réponds UNIQUEMENT à partir des passages fournis. Si la réponse n'y est pas, dis simplement que tu n'as pas cette information et conseille d'en parler à un agent de santé.
- Tu ne poses JAMAIS de diagnostic et tu ne prescris aucun médicament ni traitement.
- Si la personne décrit un symptôme (boule, écoulement, plaie, peau d'orange, mamelon rentré, changement du sein), conseille-lui de consulter rapidement un agent de santé et de taper 2 dans le menu.
- Réponds en français très simple, en 3 à 5 phrases courtes, avec un ton chaleureux et rassurant, sans jargon médical.
- Ne mentionne pas les "passages" ou les "documents"."""

MESSAGE_INCONNU = (
    "Je n'ai pas d'information fiable pour répondre à cette question. "
    "Parlez-en à un agent de santé : il saura vous répondre. "
    "Tapez 0 pour revenir au menu."
)


MOTS_VIDES = (
    "a à au aux avec ce ces cet cette d de des du elle en est et être il ils je la le les leur "
    "lui ma me mes mon ne ni nos notre nous on ou où par pas pour qu que quel quelle quels "
    "quelles qui sa se ses si son sont sur ta te tes toi ton tu un une vos votre vous y c "
    "est-ce ça ca cela faut peut peux fait faire comment combien quoi quand dois doit aux ai avoir"
).split()
MOTS_VIDES = sorted({"".join(c for c in unicodedata.normalize("NFKD", m) if not unicodedata.combining(c)) for m in MOTS_VIDES})


def decouper(texte: str, taille_max: int = 1200) -> list[str]:
    """Un passage = une section (titre # + son texte). Coupe les sections trop longues."""
    passages = []
    for section in re.split(r"\n(?=#)", texte):
        section = section.strip()
        if not section:
            continue
        if len(section) <= taille_max:
            passages.append(section)
            continue
        titre = section.splitlines()[0]
        courant = ""
        for paragraphe in re.split(r"\n\s*\n", section):
            if len(courant) + len(paragraphe) > taille_max and courant:
                passages.append(courant.strip())
                courant = titre + "\n"
            courant += "\n" + paragraphe
        passages.append(courant.strip())
    return passages


def nettoyer_markdown(texte: str) -> str:
    texte = re.sub(r"^#+\s*", "", texte, flags=re.M)
    return texte.replace("**", "").strip()


class RAG:
    def __init__(self, dossier: Path = config.DOSSIER_DOCS):
        self.passages: list[str] = []
        for fichier in sorted(dossier.glob("*")):
            if fichier.suffix.lower() in (".md", ".txt") and not fichier.name.startswith("_"):
                self.passages += decouper(fichier.read_text(encoding="utf-8"))
        if not self.passages:
            raise RuntimeError(f"Aucun document trouvé dans {dossier}")

        self.vectoriseur = TfidfVectorizer(
            strip_accents="unicode", lowercase=True, ngram_range=(1, 2),
            stop_words=MOTS_VIDES, token_pattern=r"(?u)\b\w\w+\b",
        )
        self.matrice = self.vectoriseur.fit_transform(self.passages)

        self.client = None
        if config.LLM_API_KEY:
            from openai import OpenAI
            self.client = OpenAI(api_key=config.LLM_API_KEY, base_url=config.LLM_BASE_URL)

    def rechercher(self, question: str, k: int = NB_PASSAGES):
        scores = cosine_similarity(self.vectoriseur.transform([question]), self.matrice)[0]
        meilleurs = scores.argsort()[::-1][:k]
        return [(self.passages[i], float(scores[i])) for i in meilleurs if scores[i] >= SEUIL_PERTINENCE]

    def repondre(self, question: str) -> str:
        trouves = self.rechercher(question)
        if not trouves:
            return MESSAGE_INCONNU

        if self.client is None:
            return nettoyer_markdown(trouves[0][0])

        contexte = "\n\n---\n\n".join(p for p, _ in trouves)
        try:
            resultat = self.client.chat.completions.create(
                model=config.LLM_MODEL,
                temperature=0.2,
                max_tokens=1500,
                messages=[
                    {"role": "system", "content": PROMPT_SYSTEME},
                    {"role": "user", "content": f"Passages :\n{contexte}\n\nQuestion : {question}"},
                ],
            )
            texte_ia = (resultat.choices[0].message.content or "").strip()
            return texte_ia or nettoyer_markdown(trouves[0][0])
        except Exception as erreur:  # pas d'internet, quota dépassé... on reste utile
            print(f"[RAG] Erreur LLM, réponse extractive : {erreur}")
            return nettoyer_markdown(trouves[0][0])
