"""Read matching rows without changing the teacher's workbook."""
import argparse, json
from pathlib import Path
import openpyxl

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("workbook",type=Path);p.add_argument("--name",required=True)
    args=p.parse_args()
    f=openpyxl.load_workbook(args.workbook,data_only=False,read_only=True)
    v=openpyxl.load_workbook(args.workbook,data_only=True,read_only=True)
    matches=[]
    for s in v:
        for row in s:
            if any(str(c.value).strip().casefold()==args.name.strip().casefold() for c in row):
                matches.append({"sheet":s.title,"row":row[0].row,"cells":[
                    {"address":c.coordinate,"value":c.value,"formula_or_value":f[s.title][c.coordinate].value,"number_format":c.number_format}
                    for c in row if c.value is not None]})
    print(json.dumps({"matches":matches,"count":len(matches),"note":"Inspect headers and units. Do not silently choose if count is not one."},ensure_ascii=False,indent=2,default=str))
    f.close();v.close()
    if len(matches)!=1: raise SystemExit(2)
if __name__=="__main__":main()
