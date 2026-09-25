"""Create a public ZIP from an explicit allowlist, excluding personal and legacy data."""
import argparse,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
FILES=["README.md","AGENTS.md","LICENSE","NOTICE.md",".gitignore","requirements.txt"]
DIRS=["docs","templates","reference_code","data","examples","scripts"]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path);args=p.parse_args()
    out=args.output.resolve()
    if out.exists():p.error("Output already exists; choose a new filename")
    if out.suffix.lower()!=".zip":p.error("Output must be a ZIP")
    selected=[ROOT/f for f in FILES]
    for name in DIRS:
        selected += [f for f in (ROOT/name).rglob("*") if f.is_file() and "__pycache__" not in f.parts and f.suffix!=".pyc"]
    selected += [ROOT/d/".gitkeep" for d in ["inputs","work","outputs"]]
    selected += [ROOT/"inputs"/"README.md"]
    for f in selected:
        if f.is_symlink() or not f.is_file() or not f.resolve().is_relative_to(ROOT):
            raise RuntimeError("Invalid package file: "+str(f))
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,"x",zipfile.ZIP_DEFLATED) as z:
        for f in sorted(selected):
            z.write(f,Path("ship-course-ai-pack")/f.relative_to(ROOT))
    print("Public ZIP created:",out)
    print("Files:",len(selected),"Bytes:",out.stat().st_size)
if __name__=="__main__":main()
