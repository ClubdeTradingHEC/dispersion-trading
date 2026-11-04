"""Export committed GitHub ZIP contents, or an explicitly labelled working candidate."""
from pathlib import Path
import argparse
import io
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'.gitignore','.gitattributes','.python-version','AGENTS.md','README.md','pyproject.toml','uv.lock'}
SOURCE_DIRS = {'src','scripts','tests','configs','docs','.github'}
SUFFIXES = {'.py','.json','.md','.toml','.yml','.yaml'}
MARKERS = {'data/.gitkeep','strategy/.gitkeep','backtest/.gitkeep','important_data/README.md'}


# A candidate is selected deliberately; ignore runtime files even inside source trees.
def source_files(root):
    files = []
    candidates = [root/p for p in ROOT_FILES|MARKERS]
    candidates += [p for directory in SOURCE_DIRS if (root/directory).is_dir() for p in (root/directory).rglob('*')]
    for p in candidates:
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if rel.parts[0] not in SOURCE_DIRS and rel.as_posix() not in ROOT_FILES|MARKERS:
            continue
        if any(part in {'__pycache__','.venv','.git','.pytest_cache'} for part in rel.parts):
            continue
        if rel.as_posix() in ROOT_FILES|MARKERS or p.suffix in SUFFIXES:
            if p.is_symlink():
                raise ValueError('SOURCE_SYMLINK_REQUIRES_REVIEW')
            files.append(rel)
    return sorted(files)


# The final export reads Git only. It never stages, commits, changes refs or pushes.
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='dist/dispersion-research')
    parser.add_argument('--working-tree', action='store_true', help='Review candidate, not a committed GitHub snapshot')
    args = parser.parse_args(argv)
    target = (ROOT/args.output).resolve()
    if not target.is_relative_to(ROOT/'dist') or target.exists():
        raise ValueError('Choose a new output folder inside dist/')
    target.parent.mkdir(parents=True,exist_ok=True)
    if args.working_tree:
        target.mkdir()
        for rel in source_files(ROOT):
            (target/rel).parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/rel,target/rel)
        print(f'Working-tree source candidate: {target}')
        return
    # A Windows checkout may enable autocrlf; GitHub archives use repository
    # bytes. Disable that local conversion without changing the user's settings.
    archive = subprocess.check_output(['git','-c','core.autocrlf=false','archive','--format=tar','HEAD'],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar.getmembers():
            rel = Path(member.name)
            if member.issym() or member.islnk() or rel.is_absolute() or '..' in rel.parts:
                raise ValueError('UNSAFE_GIT_ARCHIVE_ENTRY')
            if member.isfile() and not (rel.as_posix() in ROOT_FILES|MARKERS or
                    rel.parts[0] in SOURCE_DIRS and rel.suffix in SUFFIXES):
                raise ValueError('NON_SOURCE_FILE_IN_COMMIT: '+member.name)
        target.mkdir()
        tar.extractall(target,filter='data')
    print(f'Committed source export: {target}')


if __name__ == '__main__':
    main()
