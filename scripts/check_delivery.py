"""Check the public delivery-folder contract: one DWG and one Russian XLSX."""
import argparse
import json
from pathlib import Path


def check(directory, student_name):
    directory = Path(directory)
    issues = []
    if not student_name or Path(student_name).name != student_name or any(c in student_name for c in '/\\'):
        issues.append('student name must be a non-empty file-name component')
        return {'ok': False, 'issues': issues, 'expected': []}
    expected = {f'{student_name}_проект.dwg', f'{student_name}_расчёты.xlsx'}
    if not directory.is_dir():
        return {'ok': False, 'issues': [f'delivery directory does not exist: {directory}'], 'expected': sorted(expected)}
    entries = list(directory.iterdir())
    actual = {p.name for p in entries if p.is_file()}
    non_files = [p.name for p in entries if not p.is_file()]
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        issues.append('missing: ' + ', '.join(missing))
    if extra:
        issues.append('unexpected files: ' + ', '.join(extra))
    if non_files:
        issues.append('unexpected subdirectories: ' + ', '.join(sorted(non_files)))
    if any('RU' in name or 'CN' in name for name in actual):
        issues.append('version markers RU/CN are not allowed in delivery names')
    return {'ok': not issues, 'issues': issues, 'expected': sorted(expected), 'actual': sorted(actual)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('student_name')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = check(args.directory, args.student_name)
    if args.report:
        if args.report.exists():
            parser.error('report exists; choose a new path')
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)


if __name__ == '__main__':
    main()
