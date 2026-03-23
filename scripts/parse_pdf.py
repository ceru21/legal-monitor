from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pdfplumber

from models import ParsedRow
from utils import normalize_text, sha256_file, write_json

RADICADO_RE = re.compile(r"\b\d{23}\b")
FECHA_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
ACTUACION_LINE_RE = re.compile(r"^Auto\b", re.IGNORECASE)
X_CLASS_MIN = 180
X_DEMANDANTE_MIN = 296
X_DEMANDADO_MIN = 410
X_DESC_MIN = 524
X_FECHA_MIN = 775

COMMON_CLASSES = [
    "Verbal sumario",
    "Verbal",
    "Ordinario",
    "Ejecutivo con Título Hipotecario",
    "Ejecutivo con Titulo Hipotecario",
    "Ejecutivo Singular",
    "Ejecutivo",
    "Insolvencia de Persona Natural",
    "Insolvencia",
    "Reorganización Empresarial",
    "Reorganizacion Empresarial",
    "Expropiación",
    "Expropiacion",
    "Exhortos",
    "Divisorios",
    "Otros",
    "Tutelas",
    "Reconocimiento de documentos",
]

VALID_ACTUACION_PREFIXES = (
    "auto",
    "sentencia tutela",
    "auto admite tutela",
    "tutelar",
    "aprobar",
)


def split_records(page_text: str) -> list[str]:
    raw_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    lines = []
    for idx, line in enumerate(raw_lines):
        norm = normalize_text(line)
        next_norm = normalize_text(raw_lines[idx + 1]) if idx + 1 < len(raw_lines) else ""
        if not norm:
            continue
        if norm.startswith("estado no.") or norm.startswith("fecha") or norm.startswith("no proceso clase de proceso"):
            continue
        if norm.startswith("la fecha") or "se fija el presente estado" in norm:
            break
        if re.fullmatch(r"\d{4}", norm) and next_norm.startswith("la fecha"):
            break
        if "de conformidad con lo previsto" in norm or "secretario" in norm:
            continue
        lines.append(line)

    if not lines:
        return []

    starts: list[int] = []
    for idx, line in enumerate(lines):
        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
        if ACTUACION_LINE_RE.match(line) and RADICADO_RE.search(next_line):
            starts.append(idx)
        elif RADICADO_RE.search(line) and (idx == 0 or not ACTUACION_LINE_RE.match(lines[idx - 1])):
            starts.append(idx)

    starts = sorted(set(starts))
    records: list[str] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        chunk = "\n".join(lines[start:end]).strip()
        if RADICADO_RE.search(chunk):
            records.append(chunk)
    return records


def infer_actuacion(record_text: str, radicado: str) -> str | None:
    lines = [line.strip() for line in record_text.splitlines() if line.strip()]
    if not lines:
        return None
    if ACTUACION_LINE_RE.match(lines[0]):
        return lines[0]
    if ACTUACION_LINE_RE.match(lines[-1]):
        return lines[-1]
    if 'sentencia tutela' in normalize_text(lines[-1]):
        return lines[-1]
    prefix = record_text.split(radicado)[0].strip()
    prefix_lines = [line.strip() for line in prefix.splitlines() if line.strip()]
    if prefix_lines:
        return prefix_lines[-1]
    for line in reversed(lines):
        if 'sentencia tutela' in normalize_text(line):
            return line
    return None


def infer_fecha(record_text: str) -> str | None:
    match = FECHA_RE.search(record_text)
    return match.group(0) if match else None


def join_words(words: list[dict]) -> str | None:
    if not words:
        return None
    words = sorted(words, key=lambda w: (round(w['top'], 1), w['x0']))
    lines: list[list[str]] = []
    current_top = None
    for word in words:
        top = round(word['top'], 1)
        if current_top is None or abs(top - current_top) > 2.5:
            lines.append([word['text']])
            current_top = top
        else:
            lines[-1].append(word['text'])
    return "\n".join(" ".join(line) for line in lines).strip()


def detect_footer_top(words: list[dict]) -> float | None:
    ordered_words = sorted(words, key=lambda w: (round(w['top'], 1), w['x0']))
    lines: list[tuple[float, str]] = []
    current_top = None
    current_words: list[str] = []
    for word in ordered_words:
        top = round(word['top'], 1)
        if current_top is None or abs(top - current_top) > 2.5:
            if current_words:
                lines.append((current_top, " ".join(current_words)))
            current_top = top
            current_words = [word['text']]
        else:
            current_words.append(word['text'])
    if current_words:
        lines.append((current_top, " ".join(current_words)))

    for top, text in lines:
        norm = normalize_text(text)
        if norm.startswith("la fecha") or "se fija el presente estado" in norm:
            return top
    return None


def extract_column_fields(words: list[dict], record_text: str, radicado: str, next_radicado_top: float | None) -> dict:
    rad_word = next((w for w in words if w['text'] == radicado), None)
    if not rad_word:
        return {}

    rad_top = rad_word['top']
    auto_candidates = [w for w in words if w['text'].lower() == 'auto' and w['top'] < rad_top and rad_top - w['top'] < 25]
    start_top = max((w['top'] for w in auto_candidates), default=rad_top)

    line_tol = 3.0
    footer_top = detect_footer_top(words)
    later_auto_tops = sorted({w['top'] for w in words if w['text'].lower() == 'auto' and w['top'] > rad_top})
    end_top = (next_radicado_top - line_tol) if next_radicado_top is not None else float('inf')
    if footer_top is not None:
        end_top = min(end_top, footer_top - line_tol)
    for t in later_auto_tops:
        if (next_radicado_top is None or t < next_radicado_top - line_tol) and (footer_top is None or t < footer_top - line_tol):
            end_top = t
            break

    segment_start = min(start_top, rad_top - line_tol)
    segment = [w for w in words if segment_start <= w['top'] < end_top]
    act_words = [w for w in segment if w['top'] < rad_top - line_tol]
    clase_words = [w for w in segment if X_CLASS_MIN <= w['x0'] < X_DEMANDANTE_MIN and w['top'] >= rad_top - line_tol]
    demandante_words = [w for w in segment if X_DEMANDANTE_MIN <= w['x0'] < X_DEMANDADO_MIN and w['top'] >= rad_top - line_tol]
    demandado_words = [w for w in segment if X_DEMANDADO_MIN <= w['x0'] < X_DESC_MIN and w['top'] >= rad_top - line_tol]
    descripcion_words = [w for w in segment if X_DESC_MIN <= w['x0'] < X_FECHA_MIN and w['top'] >= rad_top - line_tol]

    return {
        'actuacion': join_words(act_words),
        'tipo_proceso_raw': join_words(clase_words),
        'demandante': join_words(demandante_words),
        'demandado': join_words(demandado_words),
        'descripcion_raw': join_words(descripcion_words),
    }


def infer_tipo_proceso(record_text: str, radicado: str, fecha: str | None) -> str | None:
    after = record_text.split(radicado, 1)[1]
    if fecha:
        after = after.split(fecha, 1)[0]
    norm = normalize_text(after)
    for clase in COMMON_CLASSES:
        if normalize_text(clase) in norm:
            return clase
    return None


def needs_manual_review(demandante: str | None, demandado: str | None, tipo_proceso: str | None, actuacion: str | None) -> str:
    if not demandante or not demandado or not tipo_proceso or not actuacion:
        return "Si"

    def tokens(text: str) -> list[str]:
        return text.replace('\n', ' ').split()

    def looks_like_short_acronym(text: str) -> bool:
        clean = text.replace('.', '').replace('\n', ' ').strip()
        return ' ' not in clean and clean.isupper() and len(clean) <= 6

    def looks_like_party_placeholder(text: str) -> bool:
        norm = normalize_text(text)
        return norm in {"indeterminados"}

    tipo_norm = normalize_text(tipo_proceso)
    if not any(normalize_text(clase) in tipo_norm or tipo_norm in normalize_text(clase) for clase in COMMON_CLASSES):
        return "Si"

    norm_act = normalize_text(actuacion)
    if not any(norm_act.startswith(prefix) for prefix in VALID_ACTUACION_PREFIXES):
        return "Si"

    demandante_tokens = tokens(demandante)
    demandado_tokens = tokens(demandado)

    if len(demandante_tokens) < 2 and not (looks_like_short_acronym(demandante) or looks_like_party_placeholder(demandante)):
        return "Si"
    if len(demandado_tokens) < 2 and not (looks_like_short_acronym(demandado) or looks_like_party_placeholder(demandado)):
        return "Si"

    if demandante.count('\n') > 3 or demandado.count('\n') > 4:
        return "Si"

    if '...' in demandante or '...' in demandado:
        return "Si"

    return "No"


def parse_pdf(pdf_path: str | Path) -> list[ParsedRow]:
    pdf_path = Path(pdf_path)
    fingerprint = sha256_file(pdf_path)
    rows: list[ParsedRow] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            records = split_records(page_text)
            radicados_in_page = [RADICADO_RE.search(record).group(0) for record in records if RADICADO_RE.search(record)]
            page_words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            rad_top_map = {}
            for word in page_words:
                if RADICADO_RE.fullmatch(word['text']):
                    rad_top_map[word['text']] = word['top']

            for row_index, record in enumerate(records, start=1):
                radicado_match = RADICADO_RE.search(record)
                radicado = radicado_match.group(0) if radicado_match else None
                fecha = infer_fecha(record)
                next_radicado_top = None
                if radicado and row_index < len(radicados_in_page):
                    next_radicado = radicados_in_page[row_index]
                    next_radicado_top = rad_top_map.get(next_radicado)

                fields = extract_column_fields(page_words, record, radicado, next_radicado_top) if radicado else {}
                descripcion_raw = fields.get('descripcion_raw')
                actuacion = fields.get('actuacion') or (infer_actuacion(record, radicado) if radicado else None)
                if not actuacion and descripcion_raw:
                    actuacion = descripcion_raw.splitlines()[0].strip()
                tipo_proceso = fields.get('tipo_proceso_raw') or (infer_tipo_proceso(record, radicado, fecha) if radicado else None)
                demandante = fields.get('demandante')
                demandado = fields.get('demandado')
                revision_manual = needs_manual_review(demandante, demandado, tipo_proceso, actuacion)
                rows.append(
                    ParsedRow(
                        pdf_fingerprint=fingerprint,
                        pdf_page_number=page_number,
                        row_index=row_index,
                        raw_columns=[record],
                        texto_fila_original=record,
                        radicado_raw=radicado,
                        radicado_normalizado=radicado,
                        demandante=demandante,
                        demandado=demandado,
                        tipo_proceso=tipo_proceso,
                        actuacion=actuacion,
                        revision_manual=revision_manual,
                        parse_mode="text",
                        parse_confidence=0.8 if radicado else 0.25,
                    )
                )
    return rows


def cli() -> None:
    parser = argparse.ArgumentParser(description="Parser inicial de PDF para publicaciones procesales")
    parser.add_argument("pdf_path")
    parser.add_argument("--out")
    args = parser.parse_args()

    rows = [row.to_dict() for row in parse_pdf(args.pdf_path)]
    if args.out:
        write_json(args.out, rows)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
