"""Windows bootstrap. All paths are relative to this project, not the author's PC."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / '.venv-win' / 'Scripts' / 'python.exe'

def run(args):
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True)

def main():
    parser = argparse.ArgumentParser(description='PCB Inspector PCBA Windows setup/start')
    parser.add_argument('action', choices=['setup', 'start'])
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--offline', action='store_true', help='Install from wheelhouse without PyPI')
    args = parser.parse_args()
    if os.name != 'nt':
        raise SystemExit('This launcher is for Windows. Use setup_windows.bat on a Windows PC.')
    if not (3, 11) <= sys.version_info[:2] <= (3, 13) or struct.calcsize('P') != 8:
        raise SystemExit('Use 64-bit Python 3.12 (supported bootstrap range: Python 3.11-3.13).')
    if args.action == 'setup':
        if not PYTHON.is_file():
            run([sys.executable, '-m', 'venv', ROOT / '.venv-win'])
        command = [PYTHON, '-m', 'pip', 'install', '--only-binary=:all:', '-r', ROOT / 'requirements.txt']
        if args.offline:
            wheels = ROOT / 'wheelhouse'
            if not wheels.is_dir():
                raise SystemExit('Offline dependencies are missing. See docs/PORTABILITY_PRIVACY.md.')
            command.extend(['--no-index', '--find-links', wheels])
        run(command)
        run([PYTHON, ROOT / 'scripts/make_demo.py'])
        run([PYTHON, ROOT / 'scripts/check_installation.py'])
        print('\nReady. Run start_windows.bat, then open http://127.0.0.1:8765', flush=True)
    else:
        if not PYTHON.is_file():
            raise SystemExit('Run setup_windows.bat first.')
        if not 1 <= args.port <= 65535:
            raise SystemExit('Port must be in 1..65535.')
        print(f'Open http://127.0.0.1:{args.port} in Edge or Chrome. Stop server with Ctrl+C.', flush=True)
        try:
            run([PYTHON, ROOT / 'backend/server.py', '--port', str(args.port)])
        except KeyboardInterrupt:
            pass

if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f'Command failed (exit {exc.returncode}). Check the output above. On DLL errors install the Microsoft Visual C++ x64 runtime.', file=sys.stderr)
        raise SystemExit(exc.returncode)
