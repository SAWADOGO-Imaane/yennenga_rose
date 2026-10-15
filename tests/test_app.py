"""Tests de l'API de l'application (sans internet) :  python -m pytest -q"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import api_app  # noqa: E402
import config  # noqa: E402
import vision  # noqa: E402

client = TestClient(api_app.app)


def envoyer(ident, texte):
    return client.post("/api/message", json={"id": ident, "texte": texte}).json()["messages"]


def fausse_photo(tmp_path):
    chemin = tmp_path / "photo.jpg"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=pink:s=1600x1200",
                    "-frames:v", "1", str(chemin)], check=True)
    return chemin


def test_menu_en_boutons():
    envoyer("t-menu", "/start")
    messages = envoyer("t-menu", "3")
    menu = messages[-1]
    assert len(menu["choix"]) == 7 and menu["choix"][0]["valeur"] == "1"
    assert "1 🖐️" not in menu["texte"]  # les choix sont des boutons, pas du texte


def test_orientation_jamais_de_diagnostic():
    o = vision.orientation({"image_utilisable": True, "signes": {"mamelon_rentre": True}})
    assert o["issue"] == "consulter" and o["questions"] == ["mamelon"]
    for issue in ({"image_utilisable": True, "signes": {}}, {"image_utilisable": False}, o):
        texte = vision.message_orientation(issue if "issue" in issue else vision.orientation(issue)).lower()
        assert "cancer" not in texte or "pas un diagnostic" in texte


def test_analyse_signe_visible_propose_les_centres(monkeypatch, tmp_path):
    monkeypatch.setattr(vision, "analyser_images",
                        lambda images: {"image_utilisable": True, "signes": {"peau_orange": True}})
    photo = fausse_photo(tmp_path)
    r = client.post("/api/analyse", data={"id": "t-photo"},
                    files=[("fichiers", ("p.jpg", photo.read_bytes(), "image/jpeg"))]).json()
    assert r["analyse"]["issue"] == "consulter"
    assert any("Ouagadougou" in b["libelle"] for m in r["messages"] for b in m["choix"])
    # aucune image gardée sur le serveur
    assert not list(config.DOSSIER_TMP.glob("app_*")) and not list(config.DOSSIER_TMP.glob("img_*"))


def test_analyse_impossible_bascule_sur_le_questionnaire(monkeypatch, tmp_path):
    def panne(images):
        raise RuntimeError("pas de réseau")
    monkeypatch.setattr(vision, "analyser_images", panne)
    photo = fausse_photo(tmp_path)
    r = client.post("/api/analyse", data={"id": "t-panne"},
                    files=[("fichiers", ("p.jpg", photo.read_bytes(), "image/jpeg"))]).json()
    assert r["analyse"] is None and "(1/10)" in r["messages"][-1]["texte"]


def test_son_refuse_les_fichiers_hors_audios():
    assert client.get("/api/son/config.py").status_code == 404
