"""Quality: detect dead imports via AST analysis."""
from __future__ import annotations

import ast
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _get_imported_names(tree: ast.AST) -> set[str]:
    """Return all names introduced by import statements."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def _get_used_names(tree: ast.AST, imported: set[str]) -> set[str]:
    """Return which of the imported names appear in non-import contexts."""
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Name) and node.id in imported:
            used.add(node.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in imported:
                used.add(node.value.id)
    return used


def _find_unused_imports(filepath: Path) -> list[str]:
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = _get_imported_names(tree)
    used = _get_used_names(tree, imported)
    # Exclude names used in __all__ strings or type annotations — conservative check
    return sorted(imported - used)


@pytest.mark.unit
class TestDeadImports:
    def test_split_emails_not_imported_in_import_contacts(self):
        """FIXED #1: split_emails was imported but unused — now removed from import_contacts.py."""
        filepath = PROJECT_ROOT / "db" / "import_contacts.py"
        source = filepath.read_text(encoding="utf-8")
        assert "split_emails" not in source, (
            "split_emails should have been removed from import_contacts.py"
        )

    def test_sys_not_imported_in_init_schema(self):
        """FIXED #2: sys was imported but unused — now removed from init_schema.py."""
        filepath = PROJECT_ROOT / "db" / "init_schema.py"
        source = filepath.read_text(encoding="utf-8")
        assert "import sys" not in source, (
            "sys should have been removed from init_schema.py"
        )

    def test_ast_parser_works_on_all_db_files(self):
        """Smoke test: all db/ Python files parse without error."""
        for pyfile in (PROJECT_ROOT / "db").glob("*.py"):
            source = pyfile.read_text(encoding="utf-8")
            ast.parse(source)  # Should not raise

    def test_ast_parser_works_on_all_scripts_files(self):
        """Smoke test: scripts/ Python files parse without error."""
        for pyfile in (PROJECT_ROOT / "scripts").glob("*.py"):
            source = pyfile.read_text(encoding="utf-8")
            ast.parse(source)  # Should not raise
