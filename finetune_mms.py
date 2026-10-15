"""
Transfer learning : adapter MMS (Meta) à VOS données en mooré ou dioula.

Principe : MMS-1B est un gros modèle (1 milliard de paramètres) déjà entraîné sur
1 100 langues. On GÈLE tout le modèle et on ré-entraîne seulement le petit
"adaptateur" de la langue (~2 millions de paramètres). Résultat : quelques heures
de données suffisent, et l'entraînement tient sur un seul GPU (Colab T4 compris).

1) Préparer les données :
   donnees_mos/
   ├── metadata.csv          # 2 colonnes : fichier,transcription
   ├── audio_0001.wav
   └── ...
   Exemple de metadata.csv :
       fichier,transcription
       audio_0001.wav,m tara bãag m yaoor pʋgẽ
       audio_0002.wav,ẽẽ

2) Installer (sur la machine avec GPU) :
   pip install torch transformers librosa soundfile jiwer safetensors accelerate

3) Lancer :
   python finetune_mms.py --donnees donnees_mos --langue mos --sortie modele_mms_burkina

4) Utiliser dans le bot (.env) :
   ACTIVER_MMS=1
   MMS_MODEL=modele_mms_burkina
"""
import argparse
import csv
import random
import re
import unicodedata
from pathlib import Path

import jiwer
import librosa
import torch
from safetensors.torch import save_file
from transformers import AutoProcessor, Trainer, TrainingArguments, Wav2Vec2ForCTC

MODELE_BASE = "facebook/mms-1b-all"


# ---------------------------------------------------------------
# Données
# ---------------------------------------------------------------
def normaliser(texte: str, vocab: set) -> str:
    """Minuscules, Unicode normalisé, et uniquement les caractères connus du modèle."""
    texte = unicodedata.normalize("NFC", texte.lower().strip())
    texte = re.sub(r"[,.;:!?«»\"“”()\[\]]", " ", texte)
    texte = re.sub(r"\s+", " ", texte)
    return "".join(c for c in texte if c in vocab or c == " ").strip()


def charger_exemples(dossier: Path, processor, vocab: set):
    exemples, ignores = [], 0
    with open(dossier / "metadata.csv", encoding="utf-8") as f:
        for ligne in csv.DictReader(f):
            texte = normaliser(ligne["transcription"], vocab)
            chemin = dossier / ligne["fichier"]
            if not texte or not chemin.exists():
                ignores += 1
                continue
            signal, _ = librosa.load(str(chemin), sr=16000, mono=True)
            if len(signal) > 16000 * 20:  # on évite les audios de plus de 20 s
                ignores += 1
                continue
            exemples.append({
                "input_values": processor(signal, sampling_rate=16000).input_values[0],
                "labels": processor.tokenizer(texte).input_ids,
                "texte": texte,
            })
    print(f"{len(exemples)} exemples chargés, {ignores} ignorés")
    return exemples


class Collateur:
    """Met les audios et les transcriptions d'un lot à la même longueur."""

    def __init__(self, processor):
        self.processor = processor

    def __call__(self, lot):
        audios = self.processor.feature_extractor.pad(
            [{"input_values": x["input_values"]} for x in lot], padding=True, return_tensors="pt")
        etiquettes = self.processor.tokenizer.pad(
            [{"input_ids": x["labels"]} for x in lot], padding=True, return_tensors="pt")
        labels = etiquettes["input_ids"].masked_fill(etiquettes["attention_mask"].ne(1), -100)
        audios["labels"] = labels
        return audios


# ---------------------------------------------------------------
# Évaluation : taux d'erreur sur les mots (WER), avant / après
# ---------------------------------------------------------------
@torch.no_grad()
def evaluer(model, processor, exemples, appareil):
    model.eval()
    predictions, references = [], []
    for ex in exemples:
        entree = torch.tensor([ex["input_values"]], device=appareil)
        ids = torch.argmax(model(entree).logits, dim=-1)[0]
        predictions.append(processor.decode(ids))
        references.append(ex["texte"])
    return jiwer.wer(references, predictions), list(zip(references, predictions))[:5]


# ---------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--donnees", required=True, help="dossier avec metadata.csv et les audios")
    p.add_argument("--langue", required=True, choices=["mos", "dyu"])
    p.add_argument("--sortie", default="modele_mms_burkina")
    p.add_argument("--epoques", type=int, default=4)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--batch", type=int, default=8)
    args = p.parse_args()

    appareil = "cuda" if torch.cuda.is_available() else "cpu"
    if appareil == "cpu":
        print("⚠️  Pas de GPU détecté : l'entraînement sera TRÈS lent.")

    # 1. Modèle + adaptateur EXISTANT de la langue (on part de ce que MMS sait déjà)
    processor = AutoProcessor.from_pretrained(MODELE_BASE, target_lang=args.langue)
    model = Wav2Vec2ForCTC.from_pretrained(
        MODELE_BASE, target_lang=args.langue, ignore_mismatched_sizes=True,
        attention_dropout=0.0, hidden_dropout=0.0, feat_proj_dropout=0.0,
        layerdrop=0.0, ctc_loss_reduction="mean",
    ).to(appareil)
    vocab = set(processor.tokenizer.get_vocab().keys())

    # 2. Données
    exemples = charger_exemples(Path(args.donnees), processor, vocab)
    random.seed(42)
    random.shuffle(exemples)
    n_test = max(1, len(exemples) // 10)
    test, entrainement = exemples[:n_test], exemples[n_test:]
    print(f"Entraînement : {len(entrainement)}  |  Test : {len(test)}")

    wer_avant, _ = evaluer(model, processor, test, appareil)
    print(f"\n📊 WER AVANT adaptation : {wer_avant:.1%}\n")

    # 3. Transfer learning : on gèle tout sauf l'adaptateur de langue
    model.freeze_base_model()
    for parametre in model._get_adapters().values():
        parametre.requires_grad = True
    entrainables = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"Paramètres entraînés : {entrainables:,} (sur {model.num_parameters():,})")

    arguments = TrainingArguments(
        output_dir=f"{args.sortie}_checkpoints",
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=2,
        num_train_epochs=args.epoques,
        learning_rate=args.lr,
        warmup_steps=50,
        fp16=(appareil == "cuda"),
        logging_steps=10,
        save_strategy="no",
        remove_unused_columns=False,
        report_to=[],
    )
    trainer = Trainer(model=model, args=arguments, train_dataset=entrainement,
                      data_collator=Collateur(processor))
    trainer.train()

    # 4. Résultat
    wer_apres, exemples_pred = evaluer(model, processor, test, appareil)
    print(f"\n📊 WER AVANT : {wer_avant:.1%}   →   APRÈS : {wer_apres:.1%}")
    for ref, pred in exemples_pred:
        print(f"   attendu : {ref}\n   obtenu  : {pred}\n")

    # 5. Sauvegarde (format compatible avec audio.py du bot)
    sortie = Path(args.sortie)
    model.save_pretrained(sortie)
    processor.save_pretrained(sortie)
    save_file(model._get_adapters(), sortie / f"adapter.{args.langue}.safetensors")
    print(f"✅ Modèle sauvegardé dans {sortie}/  →  dans .env : MMS_MODEL={sortie}")


if __name__ == "__main__":
    main()
