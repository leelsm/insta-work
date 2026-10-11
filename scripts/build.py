"""Build on the target OS after frontend build. Signing is a separate release step."""
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if not (root / 'frontend/dist/index.html').exists():
    raise SystemExit('먼저 frontend에서 npm ci와 npm run build를 실행하세요.')
subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
    '--name', 'ContentStudio', '--add-data', f'{root / "frontend/dist"}{os.pathsep}frontend/dist',
    '--icon', str(root / 'resources' / ('ContentStudio.ico' if os.name == 'nt' else 'ContentStudio.icns')),
    '--add-data', f'{root / "docs"}{os.pathsep}docs',
    '--add-data', f'{root / "resources"}{os.pathsep}resources',
    '--collect-all', 'imageio_ffmpeg', '--collect-all', 'keyring', '--collect-all', 'webview',
    '--hidden-import', 'uvicorn.logging', '--hidden-import', 'uvicorn.loops.auto',
    '--hidden-import', 'uvicorn.protocols.http.auto', '--hidden-import', 'uvicorn.lifespan.on',
    str(root / 'run.py')], cwd=root, check=True)
