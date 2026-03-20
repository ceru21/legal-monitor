from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
import sys

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from models import DetailDocument, Publication
from utils import normalize_text, write_json

BASE_URL = "https://publicacionesprocesales.ramajudicial.gov.co/"
START_URL = urljoin(BASE_URL, "web/publicaciones-procesales/inicio")
PORTLET_ID = "co_com_avanti_efectosProcesales_PublicacionesEfectosProcesalesPortletV2_INSTANCE_BIyXQFHVaYaq"
NS = f"_{PORTLET_ID}_"
AJAX_URL = (
    f"{START_URL}?p_p_id={PORTLET_ID}&p_p_lifecycle=2&p_p_state=normal"
    "&p_p_mode=view&p_p_cacheability=cacheLevelPage?"
)
SEARCH_URL = (
    f"{START_URL}?p_p_id={PORTLET_ID}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
    f"&{NS}action=busqueda"
)
HEADERS_JSON = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


class PortalClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.get(BASE_URL, timeout=30)

    def ajax_options(self, tipo_filtro: str, id_filtro: str, id_val: str = "") -> dict:
        params = {
            f"{NS}tipoFiltro": tipo_filtro,
            f"{NS}idFiltro": id_filtro,
            f"{NS}id": id_val,
        }
        response = self.session.get(AJAX_URL, params=params, headers=HEADERS_JSON, timeout=30)
        response.raise_for_status()
        return response.json()

    def bootstrap_medellin_civil_circuito(self) -> list[dict]:
        self.ajax_options("departamento", "05", "178845807")
        self.ajax_options("municipio", "05001", "")
        self.ajax_options("entidad", "31", "178845827")
        payload = self.ajax_options("especialidad", "03", "178845875")
        items = []
        for item in payload.get("despachos", []):
            if str(item.get("id")) == "0":
                continue
            items.append(
                {
                    "id": str(item["id"]),
                    "nombre": item["nombre"],
                    "normalized_name": normalize_text(item["nombre"]),
                }
            )
        return items

    def build_search_params(
        self,
        fecha_inicio: str,
        fecha_fin: str,
        id_despacho: str | None = None,
        cur: int | None = None,
        delta: int | None = None,
    ) -> dict:
        params = {
            f"{NS}fechaInicio": fecha_inicio,
            f"{NS}fechaFin": fecha_fin,
            f"{NS}idDepto": "05",
            f"{NS}idMuni": "05001",
            f"{NS}idEntidad": "31",
            f"{NS}idEspecialidad": "03",
            f"{NS}verTotales": "true",
            f"{NS}idDeptoIdCategory": "178845807",
        }
        if id_despacho:
            params[f"{NS}idDespacho"] = id_despacho
        if cur is not None:
            params[f"{NS}cur"] = str(cur)
            params[f"{NS}resetCur"] = "false"
        if delta is not None:
            params[f"{NS}delta"] = str(delta)
        return params

    def search_html(self, fecha_inicio: str, fecha_fin: str, id_despacho: str | None = None, cur: int = 1) -> str:
        params = self.build_search_params(fecha_inicio, fecha_fin, id_despacho=id_despacho, cur=cur, delta=10)
        response = self.session.get(SEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.text

    def extract_publications(self, html_text: str, portal_page_number: int = 1) -> list[Publication]:
        rows = re.findall(r'<tr class=" col-xs-12 tramites " >(.*?)</tr>', html_text, re.S)
        publications: list[Publication] = []
        for row in rows:
            title_match = re.search(r'<div class="titulo-publicacion[^>]*>\s*<a href="([^"]+)"[^>]*title="([^"]+)"', row, re.S)
            date_match = re.search(r'Fecha de Publicación:</i>\s*([^<]+)</p>', row)
            despacho_match = re.search(r'Despacho:([^<]+)</span>', row)
            tipo_pub_match = re.search(r'Tipo de publicación:([^<]+)</span>', row)
            if not title_match:
                continue
            publication_url = html.unescape(title_match.group(1))
            title = html.unescape(title_match.group(2)).strip()
            publication_id = self._extract_query_param(publication_url, f"{NS}articleId")
            despacho = html.unescape(despacho_match.group(1)).strip() if despacho_match else None
            fecha_publicacion = date_match.group(1).strip() if date_match else None
            tipo_publicacion = html.unescape(tipo_pub_match.group(1)).strip() if tipo_pub_match else None
            publications.append(
                Publication(
                    publication_id=publication_id,
                    despacho=despacho,
                    fecha_publicacion=fecha_publicacion,
                    titulo_publicacion=title,
                    publication_url=publication_url,
                    pdf_url=None,
                    portal_page_number=portal_page_number,
                    raw_metadata={"tipo_publicacion": tipo_publicacion},
                )
            )
        return publications

    def fetch_detail_documents(self, publication_url: str) -> list[DetailDocument]:
        response = self.session.get(publication_url, timeout=30)
        response.raise_for_status()
        html_text = response.text
        docs: list[DetailDocument] = []
        seen: set[str] = set()
        for href, label in re.findall(r'<a[^>]+href="([^"]*get_file[^"]*)"[^>]*>(.*?)</a>', html_text, re.S):
            clean_label = re.sub(r'<[^>]+>', ' ', label)
            clean_label = ' '.join(html.unescape(clean_label).split())
            full_url = urljoin(BASE_URL, html.unescape(href))
            if full_url in seen:
                continue
            seen.add(full_url)
            docs.append(
                DetailDocument(
                    label=clean_label,
                    url=full_url,
                    is_primary_candidate=self._is_primary_pdf(clean_label),
                )
            )
        return docs

    @staticmethod
    def _is_primary_pdf(label: str) -> bool:
        norm = normalize_text(label)
        return any(token in norm for token in ["planilla", "estado", "estados"]) and norm.endswith(".pdf")

    @staticmethod
    def _extract_query_param(url: str, key: str) -> str | None:
        parsed = urlparse(url)
        values = parse_qs(parsed.query).get(key)
        return values[0] if values else None


def cli() -> None:
    parser = argparse.ArgumentParser(description="Scraper inicial del portal de publicaciones procesales")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-despachos", help="Lista los despachos civiles del circuito de Medellín")

    search = sub.add_parser("search", help="Busca publicaciones para un despacho")
    search.add_argument("--fecha-inicio", required=True)
    search.add_argument("--fecha-fin", required=True)
    search.add_argument("--id-despacho")
    search.add_argument("--out")

    detail = sub.add_parser("detail", help="Extrae documentos del detalle de una publicación")
    detail.add_argument("publication_url")
    detail.add_argument("--out")

    args = parser.parse_args()
    client = PortalClient()

    if args.command == "list-despachos":
        data = client.bootstrap_medellin_civil_circuito()
        if getattr(args, "out", None):
            write_json(args.out, data)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    if args.command == "search":
        html_text = client.search_html(args.fecha_inicio, args.fecha_fin, args.id_despacho)
        publications = [p.to_dict() for p in client.extract_publications(html_text)]
        if args.out:
            write_json(args.out, publications)
        print(json.dumps(publications, ensure_ascii=False, indent=2))
        return

    if args.command == "detail":
        docs = [asdict(d) for d in client.fetch_detail_documents(args.publication_url)]
        if args.out:
            write_json(args.out, docs)
        print(json.dumps(docs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
