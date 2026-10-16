"""Package reviewed source only. Never bundle local boards, reports or environments."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import argparse

ROOT=Path(__file__).resolve().parent.parent
DIRS={'frontend','backend','config','samples','scripts','tests','docs'}
FILES={'README.md','LICENSE','.gitignore','.gitattributes','requirements.txt','setup_windows.bat','start_windows.bat'}
EXCLUDED={'__pycache__','.DS_Store','Thumbs.db','desktop.ini'}

def package(destination,with_demo):
    with ZipFile(destination,'w',ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(ROOT.rglob('*')):
            rel=path.relative_to(ROOT)
            if not path.is_file() or path.is_symlink():continue
            if any(part in EXCLUDED or part.startswith('.venv') for part in rel.parts):continue
            if not (rel.parts[0] in DIRS or len(rel.parts)==1 and path.name in FILES):continue
            if path.suffix in {'.pyc','.log','.zip','.onnx'} or path.name.startswith('.env'):continue
            if rel.parts[0]=='samples' and path.suffix=='.png' and not with_demo:continue
            archive.write(path,Path('PCB_Inspector_PCBA')/rel)
    print(f'{destination}: {destination.stat().st_size/1024:.0f} KiB')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',type=Path,default=ROOT.parent);args=parser.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    package(args.output_dir/'PCB_Inspector_PCBA_Windows.zip',True)
    package(args.output_dir/'PCB_Inspector_PCBA_Source.zip',False)
