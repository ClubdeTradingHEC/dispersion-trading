"""Keep retired engines and orphaned research code out of the supported project."""
import ast
import builtins
import json
from collections import defaultdict
from pathlib import Path
import symtable

import pytest


def test_research_modules_and_definitions_have_production_consumers():
    modules = {
        path.stem: ast.parse(path.read_text(encoding='utf-8'))
        for path in Path('src/research').glob('*.py')
    }
    edges = defaultdict(set)
    imported = defaultdict(set)
    for name, tree in modules.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                target = node.module.split('.')[-1]
                if target in modules:
                    edges[name].add(target)
                    imported[target].update(alias.name for alias in node.names)
    reachable, pending = set(), ['cli']
    while pending:
        name = pending.pop()
        if name not in reachable:
            reachable.add(name)
            pending.extend(edges[name] - reachable)
    assert set(modules) - reachable <= {'__init__'}
    for name, tree in modules.items():
        loaded = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        definitions = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        assert not definitions - loaded - imported[name], name


def test_top_level_imports_are_used():
    for path in Path('src/research').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        loaded = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        imports = {alias.asname or alias.name.split('.')[0]
                   for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in node.names}
        assert not imports - loaded, path


def test_study_configuration_has_no_ignored_settings():
    consumed = set()
    for path in Path('src/research').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                    and node.value.id == 'cfg' and isinstance(node.slice, ast.Constant)):
                consumed.add(node.slice.value)
    settings = json.loads(Path('configs/study.json').read_text())
    assert not set(settings) - consumed


def test_research_functions_do_not_reference_undefined_globals():
    implicit = {'__file__', '__name__', '__package__', '__doc__', '__spec__', '__loader__', '__builtins__'}
    for path in Path('src/research').glob('*.py'):
        table = symtable.symtable(path.read_text(encoding='utf-8'), str(path), 'exec')
        bound = {s.get_name() for s in table.get_symbols() if s.is_assigned() or s.is_imported()}
        allowed = bound | set(dir(builtins)) | implicit
        pending = list(table.get_children())
        while pending:
            scope = pending.pop()
            missing = {s.get_name() for s in scope.get_symbols()
                       if s.is_referenced() and s.is_global()} - allowed
            assert not missing, (path, scope.get_name(), missing)
            pending.extend(scope.get_children())


def test_failed_metadata_publication_keeps_previous_file(tmp_path, monkeypatch):
    from src.research.store import dump
    target = tmp_path / 'models.json'
    target.write_text('previous complete metadata', encoding='utf-8')
    def fail_replace(*args, **kwargs):
        raise OSError('deliberate publication failure')
    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(OSError, match='deliberate'):
        dump({'replacement': True}, target)
    assert target.read_text() == 'previous complete metadata'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['models.json']
