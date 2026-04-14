"""
test_blacklist.py — Casos de regresión para el filtro de blacklist.

Ejecutar:
    cd legal-monitor
    python3 -m pytest tests/test_blacklist.py -v

O sin pytest:
    python3 tests/test_blacklist.py
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
CONFIG  = Path(__file__).resolve().parent.parent / "config"
sys.path.insert(0, str(SCRIPTS))

from blacklist import BlacklistFilter, normalize

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_filter(*entries: str) -> BlacklistFilter:
    return BlacklistFilter(list(entries))


def make_records(*demandados: str) -> list[dict]:
    return [{"demandado": d, "emails_encontrados": ["x@x.com"]} for d in demandados]


# ---------------------------------------------------------------------------
# Tests: normalize()
# ---------------------------------------------------------------------------

def test_normalize_lowercase():
    assert normalize("BANCOLOMBIA") == "bancolombia"

def test_normalize_accents():
    assert normalize("Reorganización") == "reorganizacion"

def test_normalize_removes_sas():
    assert normalize("BANCOLOMBIA S.A.S.") == "bancolombia"

def test_normalize_removes_sa():
    assert normalize("Davivienda S.A.") == "davivienda"

def test_normalize_removes_ltda():
    assert normalize("EMPRESA LTDA") == "empresa"

def test_normalize_removes_eu():
    assert normalize("Ferretería Méndez E.U.") == "ferreteria mendez"

def test_normalize_removes_extra_spaces():
    assert normalize("  banco   popular  ") == "banco popular"

def test_normalize_none():
    assert normalize(None) == ""

def test_normalize_empty():
    assert normalize("") == ""


# ---------------------------------------------------------------------------
# Tests: is_blacklisted() — casos que DEBEN ser excluidos
# ---------------------------------------------------------------------------

def test_exact_match_uppercase():
    bf = make_filter("bancolombia")
    ok, match = bf.is_blacklisted("BANCOLOMBIA")
    assert ok is True
    assert match == "bancolombia"

def test_exact_match_with_sas():
    bf = make_filter("bancolombia")
    ok, match = bf.is_blacklisted("BANCOLOMBIA S.A.S.")
    assert ok is True

def test_exact_match_with_sa():
    bf = make_filter("davivienda")
    ok, match = bf.is_blacklisted("Davivienda S.A.")
    assert ok is True

def test_exact_match_with_ltda():
    bf = make_filter("banco de bogota")
    ok, match = bf.is_blacklisted("banco de bogota ltda")
    assert ok is True

def test_exact_match_mixed_case():
    bf = make_filter("bbva")
    ok, _ = bf.is_blacklisted("BBVA")
    assert ok is True

def test_exact_match_with_accents():
    bf = make_filter("reorganizacion empresarial")
    ok, _ = bf.is_blacklisted("Reorganización Empresarial S.A.S.")
    assert ok is True


# ---------------------------------------------------------------------------
# Tests: is_blacklisted() — casos que NO deben ser excluidos (exacto)
# ---------------------------------------------------------------------------

def test_no_partial_match():
    """'bbva' en blacklist NO debe excluir 'BBVA COLOMBIA' — matching exacto"""
    bf = make_filter("bbva")
    ok, _ = bf.is_blacklisted("BBVA COLOMBIA")
    assert ok is False

def test_no_partial_match_banco():
    """'banco' NO debe excluir 'banco de bogota' si solo 'banco' está en lista"""
    bf = make_filter("banco")
    ok, _ = bf.is_blacklisted("banco de bogota")
    assert ok is False

def test_no_match_similar_name():
    bf = make_filter("bancolombia")
    ok, _ = bf.is_blacklisted("BANCO COLOMBIA S.A.")
    assert ok is False

def test_no_match_unrelated():
    bf = make_filter("bancolombia", "davivienda")
    ok, _ = bf.is_blacklisted("CONSTRUCTORA LOS PINOS SAS")
    assert ok is False

def test_empty_demandado():
    bf = make_filter("bancolombia")
    ok, _ = bf.is_blacklisted(None)
    assert ok is False

def test_empty_blacklist():
    bf = make_filter()
    ok, _ = bf.is_blacklisted("BANCOLOMBIA")
    assert ok is False


# ---------------------------------------------------------------------------
# Tests: apply() — sobre lista de registros
# ---------------------------------------------------------------------------

def test_apply_marks_blacklisted():
    bf = make_filter("bancolombia")
    records = make_records("BANCOLOMBIA S.A.", "CONSTRUCTORA LOS PINOS")
    result = bf.apply(records)
    assert result[0]["blacklisted"] is True
    assert result[0]["blacklist_match"] == "bancolombia"
    assert result[1]["blacklisted"] is False
    assert result[1]["blacklist_match"] is None

def test_apply_does_not_remove_records():
    """Los registros blacklisteados deben aparecer, solo marcados."""
    bf = make_filter("bancolombia")
    records = make_records("BANCOLOMBIA", "EMPRESA LIMPIA")
    result = bf.apply(records)
    assert len(result) == 2

def test_apply_preserves_original_fields():
    bf = make_filter("bancolombia")
    records = [{"demandado": "BANCOLOMBIA", "radicado_normalizado": "12345", "emails_encontrados": ["x@x.com"]}]
    result = bf.apply(records)
    assert result[0]["radicado_normalizado"] == "12345"

def test_apply_empty_records():
    bf = make_filter("bancolombia")
    assert bf.apply([]) == []

def test_apply_multiple_blacklisted():
    bf = make_filter("bancolombia", "davivienda", "bbva")
    records = make_records("BANCOLOMBIA S.A.", "Davivienda S.A.", "BBVA", "EMPRESA LIMPIA")
    result = bf.apply(records)
    blacklisted = [r for r in result if r["blacklisted"]]
    clean = [r for r in result if not r["blacklisted"]]
    assert len(blacklisted) == 3
    assert len(clean) == 1


# ---------------------------------------------------------------------------
# Tests: carga desde YAML real
# ---------------------------------------------------------------------------

def test_load_from_yaml():
    yaml_path = CONFIG / "blacklist.yaml"
    if not yaml_path.exists():
        print("SKIP: blacklist.yaml no encontrado")
        return
    bf = BlacklistFilter.from_yaml(yaml_path)
    # Bancolombia debe estar en la lista por defecto
    ok, _ = bf.is_blacklisted("BANCOLOMBIA S.A.")
    assert ok is True

def test_load_from_missing_yaml():
    """Si el archivo no existe, retorna filtro vacío sin error."""
    bf = BlacklistFilter.from_yaml("/tmp/no_existe.yaml")
    ok, _ = bf.is_blacklisted("BANCOLOMBIA")
    assert ok is False


# ---------------------------------------------------------------------------
# Runner sin pytest
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗  {t.__name__} — {e}")
            failed += 1
        except Exception as e:
            print(f"  ✗  {t.__name__} — ERROR: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
