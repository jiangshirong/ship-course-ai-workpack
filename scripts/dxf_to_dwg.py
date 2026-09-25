"""Save a DXF as a new DWG with installed AutoCAD. Does not verify engineering correctness."""
import argparse
import sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path);p.add_argument("output",type=Path)
    p.add_argument("--progid",default="AutoCAD.Application")
    args=p.parse_args();src=args.source.resolve();out=args.output.resolve()
    if not src.is_file() or src.suffix.lower()!=".dxf":p.error("Source must be an existing DXF")
    if out.suffix.lower()!=".dwg":p.error("Output must have .dwg extension")
    if out.exists():p.error("Refusing to overwrite an existing file")
    import pythoncom
    from win32com.client import dynamic
    pythoncom.CoInitialize()
    doc=None
    stage='connect'
    def raw(o):return getattr(o,'_oleobj_',o)
    def get(o,name):return raw(o).Invoke(raw(o).GetIDsOfNames(name),0,pythoncom.DISPATCH_PROPERTYGET,True)
    def call(o,name,*values):return raw(o).Invoke(raw(o).GetIDsOfNames(name),0,pythoncom.DISPATCH_METHOD,True,*values)
    try:
        app=dynamic.Dispatch(args.progid)
        docs=get(app,'Documents')
        for i in range(get(docs,'Count')):
            existing=call(docs,'Item',i);name=get(existing,'FullName')
            if name and Path(name).resolve()==src:
                raise RuntimeError("Source is already open. Close it yourself or use a separate DXF copy.")
        out.parent.mkdir(parents=True,exist_ok=True)
        # Explicitly wrap the returned IDispatch as a document. Some pywin32
        # installations label the generic return object "Open" and do not
        # discover SaveAs as a method automatically. Do not use ActiveDocument:
        # the user can switch to a different drawing while conversion runs.
        stage='open DXF'
        # Explicit IDispatch invocation also avoids missing method/property
        # metadata on returned Open/ModelSpace wrappers in some installations.
        doc=call(docs,'Open',str(src))
        call(doc,'SetVariable','TILEMODE',1)
        # ac2018_dwg=64. This explicitly requests DWG, rather than relying on the active DXF's format.
        stage='SaveAs DWG'
        call(doc,'SaveAs',str(out),64)
        stage='close owned document'
        call(doc,'Close',False);doc=None
        if not out.is_file() or out.read_bytes()[:6] != b"AC1032":
            raise RuntimeError("AutoCAD did not produce the requested 2018 DWG; inspect the output")
        print("DWG saved. Open the saved drawing for visual and engineering checks:",out)
    except Exception as exc:
        print(f'Conversion failed at {stage}: {type(exc).__name__}: {exc}',file=sys.stderr)
        print('See docs/AutoCAD转换排障.md. Verify AutoCAD is installed, no modal dialog is active, and the requested ProgID matches. You may manually open the DXF and Save As a NEW DWG; record that conversion was manual. Do not rename extensions or overwrite existing drawings.',file=sys.stderr)
        raise SystemExit(1)
    finally:
        if doc is not None:
            try:call(doc,'Close',False)
            except Exception as exc:print(f'Could not close our conversion document: {exc}. Close only that document manually.',file=sys.stderr)
        pythoncom.CoUninitialize()
if __name__=="__main__":main()
