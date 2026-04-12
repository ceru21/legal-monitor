from __future__ import annotations

import argparse
import json
import logging
from difflib import SequenceMatcher
from pathlib import Path

from models import MatchDecision
from utils import normalize_text, write_json

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_config() -> tuple[dict, dict, float, float]:
    default_process: dict = {"verbal": ["verbal", "verbal sumario"]}
    default_actuacion: dict = {
        "admite_demanda": ["auto admite", "auto admite demanda", "admite demanda"],
        "mandamiento": ["auto libra mandamiento", "libra mandamiento", "libra mandamiento de pago", "mandamiento de pago"],
    }
    default_accept = 0.90
    default_review = 0.80

    try:
        import yaml
    except ImportError:
        return default_process, default_actuacion, default_accept, default_review

    try:
        process_terms = default_process
        actuacion_terms = default_actuacion

        patterns_path = _CONFIG_DIR / "target_patterns.yaml"
        if patterns_path.exists():
            data = yaml.safe_load(patterns_path.read_text(encoding="utf-8"))
            if data.get("process_type_patterns"):
                process_terms = {p["id"]: p["terms"] for p in data["process_type_patterns"]}
            if data.get("actuacion_patterns"):
                actuacion_terms = {p["id"]: p["terms"] for p in data["actuacion_patterns"]}

        accept_threshold = default_accept
        review_threshold = default_review
        pipeline_path = _CONFIG_DIR / "pipeline.yaml"
        if pipeline_path.exists():
            cfg = yaml.safe_load(pipeline_path.read_text(encoding="utf-8"))
            matching = cfg.get("matching", {})
            accept_threshold = float(matching.get("fuzzy_threshold_accept", default_accept))
            review_threshold = float(matching.get("fuzzy_threshold_review", default_review))

        return process_terms, actuacion_terms, accept_threshold, review_threshold

    except Exception as exc:
        logger.warning("Failed to load YAML config: %s — using defaults", exc)
        return default_process, default_actuacion, default_accept, default_review


PROCESS_TERMS, ACTUACION_TERMS, THRESHOLD_ACCEPT, THRESHOLD_REVIEW = _load_config()

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

    if revision_manual and (process_conf >= THRESHOLD_ACCEPT or act_conf >= THRESHOLD_ACCEPT):
        decision = "review"
        reason = "manual_review_required"
    elif process_conf >= THRESHOLD_ACCEPT and act_conf >= THRESHOLD_ACCEPT:
        decision = "accepted"
        reason = "strong_process_and_actuacion"
    elif process_conf >= THRESHOLD_ACCEPT or act_conf >= THRESHOLD_ACCEPT:
        decision = "accepted"
        reason = "strong_single_signal"
    elif process_conf >= THRESHOLD_REVIEW or act_conf >= THRESHOLD_REVIEW:
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
