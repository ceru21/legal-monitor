from __future__ import annotations

import argparse
import json
from difflib import SequenceMatcher
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from models import MatchDecision
from utils import normalize_text, write_json

PROCESS_TERMS = {
    "verbal": ["verbal", "verbal sumario"],
}

ACTUACION_TERMS = {
    "admite_demanda": ["auto admite", "auto admite demanda", "admite demanda"],
    "mandamiento": ["auto libra mandamiento", "libra mandamiento", "libra mandamiento de pago", "mandamiento de pago"],
}

NEGATIVE_HINTS = [
    "inadmite demanda",
    "niega mandamiento",
    "rechaza demanda",
    "rechaza solicitud",
]


def best_score(text: str, terms: list[str]) -> tuple[str | None, float]:
    norm_text = normalize_text(text)
    best_term = None
    best = 0.0
    for term in terms:
        norm_term = normalize_text(term)
        if norm_term in norm_text:
            score = 1.0
        else:
            score = SequenceMatcher(None, norm_text, norm_term).ratio()
        if score > best:
            best = score
            best_term = term
    return best_term, best


def decide(row: dict) -> MatchDecision:
    tipo = row.get("tipo_proceso") or ""
    actuacion = row.get("actuacion") or ""
    full_text = " ".join([tipo, actuacion, row.get("texto_fila_original") or ""])
    norm_full = normalize_text(full_text)
    revision_manual = (row.get("revision_manual") or "No").lower() == "si"

    for negative in NEGATIVE_HINTS:
        if normalize_text(negative) in norm_full:
            return MatchDecision(
                decision="review",
                match_reason=f"negative_hint:{negative}",
                process_type_match="verbal" if "verbal" in norm_full else None,
                actuacion_match=None,
                process_type_confidence=1.0 if "verbal" in norm_full else 0.0,
                actuacion_confidence=0.0,
            )

    process_match = None
    process_conf = 0.0
    for key, terms in PROCESS_TERMS.items():
        _, score = best_score(tipo or full_text, terms)
        if score > process_conf:
            process_match = key
            process_conf = score

    act_match = None
    act_conf = 0.0
    for key, terms in ACTUACION_TERMS.items():
        _, score = best_score(actuacion or full_text, terms)
        if score > act_conf:
            act_match = key
            act_conf = score

    if revision_manual and (process_conf >= 0.95 or act_conf >= 0.95):
        decision = "review"
        reason = "manual_review_required"
    elif process_conf >= 0.95 and act_conf >= 0.95:
        decision = "accepted"
        reason = "strong_process_and_actuacion"
    elif process_conf >= 0.95 or act_conf >= 0.95:
        decision = "accepted"
        reason = "strong_single_signal"
    elif process_conf >= 0.8 or act_conf >= 0.8:
        decision = "review"
        reason = "medium_signal"
    else:
        decision = "rejected"
        reason = "no_signal"

    return MatchDecision(
        decision=decision,
        match_reason=reason,
        process_type_match=process_match,
        actuacion_match=act_match,
        process_type_confidence=round(process_conf, 3),
        actuacion_confidence=round(act_conf, 3),
    )


def cli() -> None:
    parser = argparse.ArgumentParser(description="Matcher inicial para publicaciones procesales")
    parser.add_argument("parsed_json")
    parser.add_argument("--out")
    args = parser.parse_args()

    rows = json.loads(Path(args.parsed_json).read_text(encoding="utf-8"))
    results = []
    for row in rows:
        decision = decide(row).to_dict()
        results.append({**row, **decision})
    if args.out:
        write_json(args.out, results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
