"""Recalculate supported scalar formulas into JSON and optionally a NEW cached XLSX.
Never overwrites the source; errors abort the entire output. Not Excel validation.
"""
import argparse, json, math, posixpath, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from course_formula import Workbook, FormulaError

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'

def load(path):
    if path.suffix.lower()=='.json':
        return Workbook.from_template(str(path))
    if path.suffix.lower()!='.xlsx':raise ValueError('Expected workbook spec JSON or .xlsx')
    import openpyxl
    src=openpyxl.load_workbook(path,data_only=False)
    if src.defined_names:raise FormulaError('Defined names are unsupported')
    if src._external_links:raise FormulaError('External workbook links are unsupported')
    sheets={}
    for s in src:
        cells={}
        for row in s:
            for c in row:
                if c.value is None:continue
                if not isinstance(c.value,(str,int,float,bool)):
                    raise FormulaError(f'Unsupported cell type: {s.title}!{c.coordinate}')
                if c.data_type=='e':raise FormulaError(f'Excel error: {s.title}!{c.coordinate} {c.value}')
                if c.is_date:raise FormulaError('Date-formatted cells unsupported')
                cells[c.coordinate]=c.value
        sheets[s.title]=cells
    src.close()
    return Workbook(sheets)

def evaluate(book):
    values={};count=0
    for sn,cells in book.sheets.items():
        values[sn]={}
        for a,raw in cells.items():
            try:val=book.value(sn,a)
            except Exception as exc:raise FormulaError(f'{sn}!{a}: {exc}') from exc
            values[sn][a]=val
            count+=isinstance(raw,str) and raw.startswith('=')
    return {'engine':'course-scalar-v2','excel_validated':False,'formula_count':count,'values':values}

def write_cached_xlsx(source, output, result):
    """Patch only formula <v> and calculation flags; retain original workbook parts."""
    if source.suffix.lower()!='.xlsx':raise ValueError('--xlsx requires an XLSX input')
    if output.exists():raise FileExistsError(output)
    with zipfile.ZipFile(source) as zin:
        wb=ET.fromstring(zin.read('xl/workbook.xml'))
        # ElementTree does not preserve prefix declarations used only inside
        # extension attribute values. Refuse those workbooks rather than risk
        # damaging an Excel extension while adding basic formula caches.
        for part in ['xl/workbook.xml']+[n for n in zin.namelist() if n.startswith('xl/worksheets/') and n.endswith('.xml')]:
            if b'Ignorable=' in zin.read(part) or b'extLst' in zin.read(part):
                raise ValueError('Cache export supports basic XLSX only; use Excel/LibreOffice for extension-bearing workbooks')
        rels=ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))
        paths={r.attrib['Id']:posixpath.normpath('xl/'+r.attrib['Target']) if not r.attrib['Target'].startswith('/') else r.attrib['Target'].lstrip('/') for r in rels}
        patches={}
        for s in wb.find(f'{{{NS}}}sheets'):
            path=paths[s.attrib[f'{{{REL}}}id']];root=ET.fromstring(zin.read(path))
            for c in root.iter(f'{{{NS}}}c'):
                if c.find(f'{{{NS}}}f') is None:continue
                val=result['values'][s.attrib['name']][c.attrib['r']]
                old=c.find(f'{{{NS}}}v')
                if old is not None:c.remove(old)
                v=ET.SubElement(c,f'{{{NS}}}v')
                if isinstance(val,bool):c.set('t','b');v.text='1' if val else '0'
                elif isinstance(val,(float,int)):
                    if not math.isfinite(val):raise FormulaError('Nonfinite cache')
                    c.attrib.pop('t',None)
                    v.text=str(val)
                elif isinstance(val,str):c.set('t','str');v.text=val
                elif val is None:c.attrib.pop('t',None);v.text='0'
                else:raise FormulaError('Unsupported cached result type')
            patches[path]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
        calc=wb.find(f'{{{NS}}}calcPr')
        if calc is None:calc=ET.SubElement(wb,f'{{{NS}}}calcPr')
        calc.set('calcMode','auto');calc.set('fullCalcOnLoad','1');calc.set('forceFullCalc','1')
        patches['xl/workbook.xml']=ET.tostring(wb,encoding='utf-8',xml_declaration=True)
        output.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as zout:
            for entry in zin.infolist():zout.writestr(entry,patches.get(entry.filename,zin.read(entry.filename)))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('report',type=Path)
    p.add_argument('--xlsx',type=Path,help='Save NEW XLSX with independently computed caches; not Excel-certified')
    a=p.parse_args()
    if a.report.exists() or (a.xlsx and a.xlsx.exists()):p.error('Refusing to overwrite outputs')
    if a.report.suffix.lower()!='.json':p.error('Report must be JSON')
    if a.xlsx and (a.xlsx.suffix.lower()!='.xlsx' or a.source.suffix.lower()!='.xlsx'):p.error('--xlsx requires XLSX input and output')
    result=evaluate(load(a.source))
    if a.xlsx:write_cached_xlsx(a.source,a.xlsx,result)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    with a.report.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(f"Evaluated {result['formula_count']} formulas. Limited engine; NOT Excel validation.")
if __name__=='__main__':main()
