"""Validate local dependencies/resources without starting the HTTP application."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'backend'))
from inspection import PCBAInspector

if __name__=='__main__':
    engine=PCBAInspector(ROOT/'config/inspection.json')
    if not engine.health()['ready']:raise SystemExit(engine.error)
    for name in ['frontend/index.html','frontend/styles.css','frontend/app.js']:
        if not (ROOT/name).is_file():raise SystemExit('Missing file: '+name)
    manifest=json.loads((ROOT/'samples/manifest.json').read_text(encoding='utf-8'))
    for sample in manifest:
        for field in ['reference','file']:
            if not (ROOT/'samples'/sample[field]).is_file():raise SystemExit('Missing sample: '+sample[field])
    print('Dependencies and source files are present. OpenCV: '+engine.cv.__version__)
    print('Mode: reference comparison for assembled PCBs. No neural weights required.')
    print('To run algorithm checks: .venv-win\\Scripts\\python.exe -m unittest discover -s tests -v')
