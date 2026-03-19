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
    "Ejecutivo con Título Hipotecario",
    "Ejecutivo con Titulo Hipotecario",
    "Ejecutivo",
    "Insolvencia de Persona Natural",
    "Insolvencia",
    "Expropiación",
    "Expropiacion",
    "Exhortos",
    "Divisorios",
    "Otros",
    "Reconocimiento de documentos",
]


def split_records(page_text: str) -> list[str]:
    raw_lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    lines = []
    for line in raw_lines:
        norm = normalize_text(line)
        if not norm:
            continue
        if norm.startswith("estado no.") or norm.startswith("fecha") or norm.startswith("no proceso clase de proceso"):
            continue
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
    prefix = record_text.split(radicado)[0].strip()
    prefix_lines = [line.strip() for line in prefix.splitlines() if line.strip()]
    return prefix_lines[-1] if prefix_lines else None


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


def extract_column_fields(page, record_text: str, radicado: str, next_radicado_top: float | None) -> dict:
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    rad_word = next((w for w in words if w['text'] == radicado), None)
    if not rad_word:
        return {}

    rad_top = rad_word['top']
    auto_candidates = [w for w in words if w['text'].lower() == 'auto' and w['top'] < rad_top and rad_top - w['top'] < 25]
    start_top = max((w['top'] for w in auto_candidates), default=rad_top)

    later_auto_tops = sorted({w['top'] for w in words if w['text'].lower() == 'auto' and w['top'] > rad_top})
    end_top = next_radicado_top if next_radicado_top is not None else float('inf')
    for t in later_auto_tops:
        if next_radicado_top is None or t < next_radicado_top:
            end_top = t
            break

    segment = [w for w in words if start_top <= w['top'] < end_top]
    line_tol = 3.0
    act_words = [w for w in segment if w['top'] < rad_top - line_tol]
    clase_words = [w for w in segment if X_CLASS_MIN <= w['x0'] < X_DEMANDANTE_MIN and w['top'] >= rad_top - line_tol]
    demandante_words = [w for w in segment if X_DEMANDANTE_MIN <= w['x0'] < X_DEMANDADO_MIN and w['top'] >= rad_top - line_tol]
    demandado_words = [w for w in segment if X_DEMANDADO_MIN <= w['x0'] < X_DESC_MIN and w['top'] >= rad_top - line_tol]

    return {
        'actuacion': join_words(act_words),
        'tipo_proceso_raw': join_words(clase_words),
        'demandante': join_words(demandante_words),
        'demandado': join_words(demandado_words),
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

                fields = extract_column_fields(page, record, radicado, next_radicado_top) if radicado else {}
                actuacion = fields.get('actuacion') or (infer_actuacion(record, radicado) if radicado else None)
                tipo_proceso = fields.get('tipo_proceso_raw') or (infer_tipo_proceso(record, radicado, fecha) if radicado else None)
                rows.append(
                    ParsedRow(
                        pdf_fingerprint=fingerprint,
                        pdf_page_number=page_number,
                        row_index=row_index,
                        raw_columns=[record],
                        texto_fila_original=record,
                        radicado_raw=radicado,
                        radicado_normalizado=radicado,
                        demandante=fields.get('demandante'),
                        demandado=fields.get('demandado'),
                        tipo_proceso=tipo_proceso,
                        actuacion=actuacion,
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
