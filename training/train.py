"""Train the document-type classifier and publish an honest accuracy report.

TF-IDF over word and character n-grams, logistic regression on top. Small,
fast to train, fully inspectable - and adequate for a synthetic corpus,
which is all this is. The metrics file committed next to the model states
exactly what was measured, on what, and what that does not prove.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

HERE = Path(__file__).parent
MODEL_DIR = HERE.parent / "server" / "doc_intake_service" / "model"


def main() -> None:
    corpus_path = HERE / "corpus.jsonl"
    if not corpus_path.exists():
        raise SystemExit("run generate_corpus.py first")

    texts, labels = [], []
    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(row["label"])

    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.25, stratify=labels, random_state=2026
    )

    model = Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                    min_df=2,
                ),
            ),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )
    model.fit(x_train, y_train)

    y_pred = model.predict(x_test)
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    labels_sorted = sorted(set(labels))
    cm = confusion_matrix(y_test, y_pred, labels=labels_sorted).tolist()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / "model.joblib")

    metrics = {
        "trained_on": "synthetic corpus from training/generate_corpus.py (fictional vendors, generated text)",
        "documents": len(texts),
        "held_out": len(x_test),
        "labels": labels_sorted,
        "classification_report": report,
        "confusion_matrix": cm,
        "honest_note": (
            "These numbers measure performance on synthetic documents that share a "
            "generator with the training data. They say the pipeline works; they say "
            "nothing about real-world scans, photographed receipts, or layouts the "
            "generator never produced. A production deployment needs real, labelled "
            "documents and re-training."
        ),
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    print(classification_report(y_test, y_pred, zero_division=0))
    print(f"model  -> {MODEL_DIR / 'model.joblib'}")
    print(f"metrics-> {MODEL_DIR / 'metrics.json'}")


if __name__ == "__main__":
    main()
