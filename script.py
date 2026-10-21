# gen_tree.py
from pathlib import Path

EXCLUDE = {'.venv', '.git', '.vscode', '__pycache__', 'node_modules', '.idea'}


def walk(path: Path, prefix: str = ''):
    entries = sorted(
        [e for e in path.iterdir() if e.name not in EXCLUDE],
        key=lambda e: (e.is_file(), e.name),
    )
    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        connector = '└── ' if last else '├── '
        print(f'{prefix}{connector}{entry.name}')
        if entry.is_dir():
            extension = '    ' if last else '│   '
            walk(entry, prefix + extension)


root = Path('.')
print(root.resolve().name + '/')
walk(root)
