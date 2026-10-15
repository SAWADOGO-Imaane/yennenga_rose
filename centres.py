"""Liste des centres de santé, par ville (data/centres.json)."""
import json

from config import FICHIER_CENTRES


class Centres:
    def __init__(self, chemin=FICHIER_CENTRES):
        with open(chemin, encoding="utf-8") as f:
            self.villes = json.load(f)["villes"]

    def options(self) -> list[str]:
        """Libellés numérotés : ['1 Ouagadougou', ..., '7 Autre ville']"""
        libelles = [f"{i} {v['nom']}" for i, v in enumerate(self.villes, start=1)]
        libelles.append(f"{len(self.villes) + 1} Autre ville / village")
        return libelles

    def par_choix(self, choix: int):
        """Renvoie la ville (dict) pour un numéro, ou None pour 'Autre'."""
        if 1 <= choix <= len(self.villes):
            return self.villes[choix - 1]
        return None

    def par_nom(self, texte: str):
        t = texte.strip().lower()
        if len(t) < 3:
            return None
        for ville in self.villes:
            nom = ville["nom"].lower()
            if nom in t or t in nom or nom.split("-")[0].split()[0] in t:
                return ville
        return None

    @staticmethod
    def formater(ville: dict) -> str:
        lignes = [f"📍 {ville['nom']} :"]
        for c in ville["centres"]:
            ligne = f"• {c['nom']}"
            if c.get("service"):
                ligne += f" ({c['service']})"
            if c.get("infos"):
                ligne += f" – {c['infos']}"
            lignes.append(ligne)
        return "\n".join(lignes)
