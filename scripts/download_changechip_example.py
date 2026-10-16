"""Optional research-only download. Not called by setup and not redistributed."""
from pathlib import Path
import argparse
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
BASE='https://raw.githubusercontent.com/Scientific-Computing-Lab/ChangeChip/master/'

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Fetch publicly accessible reference/inspection example from ChangeChip')
    parser.add_argument('--acknowledge-terms',action='store_true',help='I reviewed the source terms; images are for local evaluation, not automatic redistribution')
    args=parser.parse_args()
    if not args.acknowledge_terms:
        raise SystemExit('Review https://github.com/Scientific-Computing-Lab/ChangeChip and docs/DATASETS.md. No image license is stated. Use your own photos or pass --acknowledge-terms for local evaluation.')
    folder=ROOT/'local_data/changechip';folder.mkdir(parents=True,exist_ok=True)
    for name in ['REFERENCE_IMAGE.JPG','INPUT_IMAGE.JPG']:
        target=folder/name
        with urllib.request.urlopen(BASE+name,timeout=120) as response:target.write_bytes(response.read())
        print(target)
