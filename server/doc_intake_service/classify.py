"""Document-type classification via the trained model.

The model replaces the sibling TypeScript library's keyword heuristic with
a trained classifier - and inherits an obligation the heuristic never had:
it must say how sure it is. Low confidence is not rounded up; it becomes a
failing rule and a person looks.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import joblib

MODEL_PATH = Path(__file__).parent / "model" / "model.joblib"


@dataclass
class TypePrediction:
    label: str
    confidence: float
    alternatives: list[tuple[str, float]]

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "alternatives": [(l, round(c, 4)) for l, c in self.alternatives],
        }


@lru_cache(maxsize=1)
def _model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"trained model missing at {MODEL_PATH} - run training/generate_corpus.py "
            "then training/train.py (see README)"
        )
    return joblib.load(MODEL_PATH)


def classify(text: str) -> TypePrediction:
    model = _model()
    probs = model.predict_proba([text])[0]
    ranked = sorted(zip(model.classes_, probs), key=lambda t: t[1], reverse=True)
    best_label, best_p = ranked[0]
    return TypePrediction(
        label=str(best_label),
        confidence=float(best_p),
        alternatives=[(str(l), float(p)) for l, p in ranked[1:3]],
    )
