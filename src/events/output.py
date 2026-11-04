"""Transactional publication for one dedicated event-workflow output directory."""
from contextlib import contextmanager
from pathlib import Path
import json
import tempfile
from src.research.store import _publish


# Reuse the existing rollback-tested publisher, swapping the complete owned directory.
@contextmanager
def publish_run(target, inputs, command):
    target=Path(target).resolve()
    project=Path.cwd() if (Path.cwd()/'src/events/cli.py').is_file() else Path(__file__).resolve().parents[2]
    if any(part in {'.git','.venv','__pycache__'} for part in target.parts):
        raise ValueError('Output cannot be Git metadata, an environment or a cache')
    if target==project or (target.is_relative_to(project) and target.relative_to(project).parts[0] in
                          {'src','scripts','tests','configs','docs','.github'}):
        raise ValueError('Choose an output directory outside source/configuration')
    for source in inputs:
        source=Path(source).resolve()
        if source==target or source.is_relative_to(target):
            raise ValueError('Output directory cannot contain an input file')
    if target.exists():
        if not target.is_dir():
            raise ValueError('Output must be a directory')
        if any(target.iterdir()):
            receipt=target/'run.json'
            if not receipt.is_file():
                raise ValueError('Nonempty output is not an owned event run; choose another directory')
            previous=json.loads(receipt.read_text(encoding='utf-8'))
            if previous.get('command')!=command or previous.get('status')!='PASS':
                raise ValueError('Do not mix different workflow outputs in one directory')
            # Support the first integration's receipts while refusing unrelated user files.
            known={'run.json','tables.xlsx'}
            known.update(previous.get('files',{}))
            if not previous.get('files'):
                if command=='basket':
                    known.add('basket_correlation.csv')
                    known.update(p.name for p in target.glob('basket_*.png'))
                elif command=='study':
                    known.update({'by_event_type.csv','broad_moves.csv','event_detail.csv'})
                elif command=='vix':
                    known.add('vix_overlay.csv')
                    known.update(p.name for p in target.glob('vix_*.png'))
                elif command=='macro':
                    known.add('macro_events.csv')
            if any(p.name not in known or not p.is_file() or p.is_symlink() for p in target.iterdir()):
                raise ValueError('Output contains unrelated files; preserve them and choose another directory')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.event-run-',dir=target.parent) as directory:
        staging=Path(directory)
        output=staging/target.name
        output.mkdir()
        yield output
        # run.json and all tables/charts move together; rollback retains the old generation.
        _publish(staging,target.parent)
