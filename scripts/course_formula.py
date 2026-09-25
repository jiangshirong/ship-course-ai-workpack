"""Limited, fail-closed course formula evaluator; NOT a general Excel engine.

Adapted from the user-provided trial evaluator; semantics and error handling
corrected during the package review. See docs/公式引擎与验证.md for scope.
Only ordinary A1 scalar formulas are supported. No names, arrays, dates,
external workbooks, macros or engineering approval. Cached values are never inputs.
"""
from __future__ import annotations

import json
import math
import re
from decimal import Decimal, ROUND_HALF_UP

# ---------------------------------------------------------------- tokenizer

TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<num>\d+\.\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?|\d+(?:[eE][+-]?\d+)?)
  | (?P<str>"(?:[^"]|"")*")
  | (?P<sheet>'(?:[^']|'')*'!)
  | (?P<ref>(?:[^\W\d][\w.]*!)?\$?[A-Z]{1,3}\$?\d{1,7}(?![\w.(]))
  | (?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
  | (?P<op><>|<=|>=|[+\-*/^&=<>(),:])
    """,
    re.VERBOSE,
)


class FormulaError(Exception):
    pass


def tokenize(src: str):
    pos, out = 0, []
    while pos < len(src):
        m = TOKEN_RE.match(src, pos)
        if not m:
            raise FormulaError(f"cannot tokenize at {pos}: {src[pos:pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        out.append((kind, m.group()))
    out.append(("eof", ""))
    return out


# ---------------------------------------------------------------- parser

class Parser:
    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i]

    def next(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def expect(self, val):
        kind, text = self.next()
        if text != val:
            raise FormulaError(f"expected {val!r}, got {text!r}")

    def parse(self):
        node = self.comparison()
        if self.peek()[0] != "eof":
            raise FormulaError(f"trailing tokens: {self.peek()}")
        return node

    def comparison(self):
        node = self.concat()
        while self.peek()[1] in ("=", "<>", "<", "<=", ">", ">="):
            op = self.next()[1]
            node = ("bin", op, node, self.concat())
        return node

    def concat(self):
        node = self.additive()
        while self.peek()[1] == "&":
            self.next()
            node = ("bin", "&", node, self.additive())
        return node

    def additive(self):
        node = self.multiplicative()
        while self.peek()[1] in ("+", "-"):
            op = self.next()[1]
            node = ("bin", op, node, self.multiplicative())
        return node

    def multiplicative(self):
        node = self.power()
        while self.peek()[1] in ("*", "/"):
            op = self.next()[1]
            node = ("bin", op, node, self.power())
        return node

    def unary(self):
        if self.peek()[1] == "-":
            self.next()
            return ("neg", self.unary())
        if self.peek()[1] == "+":
            self.next()
            return self.unary()
        return self.atom()

    def power(self):
        node = self.unary()
        while self.peek()[1] == "^":
            self.next()
            node = ("bin", "^", node, self.unary())
        return node

    def atom(self):
        kind, text = self.next()
        if kind == "num":
            return ("num", float(text))
        if kind == "str":
            return ("str", text[1:-1].replace('""', '"'))
        if text == "(":
            node = self.comparison()
            self.expect(")")
            return node
        if kind == "ident":
            if text.upper() in ('TRUE', 'FALSE') and self.peek()[1] != '(':
                return ('num', text.upper() == 'TRUE')
            if self.peek()[1] == "(":
                self.next()
                args = []
                if self.peek()[1] != ")":
                    args.append(self.comparison())
                    while self.peek()[1] == ",":
                        self.next()
                        args.append(self.comparison())
                self.expect(")")
                return ("call", text.upper(), args)
            if self.peek()[1] == "!":
                self.next()
                kind2, ref = self.next()
                if kind2 != "ref":
                    raise FormulaError(f"bad sheet ref after {text}!")
                return self.maybe_range(text, ref)
            return self.maybe_range(None, text)
        if kind == "sheet":
            # token includes the trailing '!' and the surrounding quotes
            sheet = text[:-1]
            if sheet.startswith("'") and sheet.endswith("'"):
                sheet = sheet[1:-1]
            sheet = sheet.replace("''", "'")
            kind2, ref = self.next()
            if kind2 != "ref":
                raise FormulaError(f"bad ref after {sheet}!")
            return self.maybe_range(sheet, ref)
        if kind == "ref":
            return self.maybe_range(None, text)
        raise FormulaError(f"unexpected token {text!r}")

    def maybe_range(self, sheet, ref):
        if self.peek()[1] != ":":
            return ("ref", sheet, ref)
        self.next()
        kind2, ref2 = self.next()
        if kind2 != "ref":
            raise FormulaError(f"bad range end {ref2!r}")
        return ("range", sheet, ref, ref2)


REF_RE = re.compile(r"^(?:([^\W\d][\w.]*)!)?\$?([A-Z]{1,3})\$?(\d{1,7})$")


def split_ref(ref: str):
    m = REF_RE.match(ref)
    if not m:
        raise FormulaError(f"bad ref {ref!r}")
    return m.group(1), m.group(2), int(m.group(3))


def col_to_num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def num_to_col(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# ---------------------------------------------------------------- workbook

class Workbook:
    def __init__(self, sheets: dict[str, dict[str, object]]):
        self.sheets = sheets
        self._cache: dict[tuple[str, str], object] = {}
        self._busy: set[tuple[str, str]] = set()

    @classmethod
    def from_template(cls, path: str) -> "Workbook":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        sheets = {}
        for s in data["sheets"]:
            cells = {}
            for c in s["cells"]:
                cells[c["address"]] = c.get("value")
            sheets[s["name"]] = cells
        return cls(sheets)

    def raw(self, sheet: str, addr: str):
        if sheet not in self.sheets:
            raise FormulaError(f"no sheet {sheet!r}")
        return self.sheets[sheet].get(addr)

    def set(self, sheet: str, addr: str, value):
        self.sheets[sheet][addr] = value
        self._cache.clear()

    def value(self, sheet: str, addr: str):
        key = (sheet, addr)
        if key in self._cache:
            return self._cache[key]
        if key in self._busy:
            raise FormulaError(f"circular reference at {sheet}!{addr}")
        raw = self.raw(sheet, addr)
        if isinstance(raw, str) and raw.startswith("="):
            self._busy.add(key)
            try:
                val = self.eval(raw[1:], sheet)
            finally:
                self._busy.discard(key)
        else:
            val = raw
        if isinstance(val, (int, float)) and not math.isfinite(val):
            raise FormulaError(f'nonfinite value at {sheet}!{addr}')
        if isinstance(val, complex):
            raise FormulaError(f'complex value at {sheet}!{addr}')
        if isinstance(val, str) and val in ('#REF!', '#VALUE!', '#DIV/0!', '#N/A', '#NAME?', '#NUM!', '#SPILL!', '#NULL!'):
            raise FormulaError(f'{val} at {sheet}!{addr}')
        self._cache[key] = val
        return val

    # ------------------------------------------------------------ evaluation

    def eval(self, formula: str, sheet: str):
        return self.node_value(Parser(tokenize(formula)).parse(), sheet)

    def node_value(self, node, sheet):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "str":
            return node[1]
        if kind == "neg":
            return -num(self.node_value(node[1], sheet))
        if kind == "ref":
            return self.ref_value(node[1] or sheet, node[2])
        if kind == "range":
            raise FormulaError("range used as a scalar value")
        if kind == "bin":
            return self.binop(node[1], node[2], node[3], sheet)
        if kind == "call":
            return self.call(node[1], node[2], sheet)
        raise FormulaError(f"bad node {node}")

    def ref_value(self, sheet, ref):
        target, col, row = split_ref(ref)
        return self.value(target or sheet, f"{col}{row}")

    def range_values(self, sheet, start, end):
        sheet2, c1, r1 = split_ref(start)
        end_sheet, c2, r2 = split_ref(end)
        sheet2 = sheet2 or sheet
        if end_sheet and end_sheet != sheet2:
            raise FormulaError('3D ranges are unsupported')
        n1, n2 = col_to_num(c1), col_to_num(c2)
        if n1 > n2:
            n1, n2 = n2, n1
        if r1 > r2:
            r1, r2 = r2, r1
        out = []
        for r in range(r1, r2 + 1):
            for c in range(n1, n2 + 1):
                out.append(self.value(sheet2, f"{num_to_col(c)}{r}"))
        return out

    def arg_values(self, args, sheet):
        """Flatten argument nodes to scalar values, expanding ranges."""
        out = []
        for a in args:
            if a[0] == "range":
                out.extend(self.range_values(a[1] or sheet, a[2], a[3]))
            else:
                out.append(self.node_value(a, sheet))
        return out

    def binop(self, op, lhs, rhs, sheet):
        if op == "&":
            return text(l(self.node_value(lhs, sheet))) + text(l(self.node_value(rhs, sheet)))
        a = self.node_value(lhs, sheet)
        b = self.node_value(rhs, sheet)
        if op in ('=', '<>', '<', '<=', '>', '>='):
            if a is None:a = '' if isinstance(b,str) else 0
            if b is None:b = '' if isinstance(a,str) else 0
            if isinstance(a,str) and isinstance(b,str):
                a,b=a.casefold(),b.casefold()
            elif isinstance(a,str) or isinstance(b,str) or isinstance(a,bool) != isinstance(b,bool):
                raise FormulaError('mixed-type comparison unsupported; make types explicit')
            return {'=':lambda:a==b,'<>':lambda:a!=b,'<':lambda:a<b,'<=':lambda:a<=b,'>':lambda:a>b,'>=':lambda:a>=b}[op]()
        a,b = num(a),num(b)
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                raise FormulaError("division by zero")
            return a / b
        if op == "^":
            return a ** b
        if op == "=":
            return cmp_eq(a, b)
        if op == "<>":
            return not cmp_eq(a, b)
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        if op == ">=":
            return a >= b
        raise FormulaError(f"bad operator {op}")

    def call(self, name, args, sheet):
        arities={'PI':(0,0),'TRUE':(0,0),'FALSE':(0,0),'IF':(2,3),'AND':(1,255),'OR':(1,255),'NOT':(1,1),
                 'SQRT':(1,1),'ABS':(1,1),'SIN':(1,1),'COS':(1,1),'ROUND':(2,2),'INT':(1,1),
                 'CEILING':(2,2),'CEILING.MATH':(1,3),'FLOOR':(2,2),
                 'SUM':(1,255),'MAX':(1,255),'MIN':(1,255),'COUNT':(1,255)}
        if name not in arities:raise FormulaError(f'unsupported function {name}')
        lo,hi=arities[name]
        if not lo <= len(args) <= hi:raise FormulaError(f'wrong argument count for {name}')
        if name == "PI":
            return math.pi
        if name in ('TRUE','FALSE'):return name == 'TRUE'
        if name == 'IF':
            chosen=1 if truthy(self.node_value(args[0],sheet)) else 2
            return self.node_value(args[chosen],sheet) if chosen < len(args) else False

        if name in ("SUM", "MAX", "MIN", "COUNT"):
            nums=[]
            for a in args:
                if a[0] in ('range','ref'):
                    vals=self.range_values(a[1] or sheet,a[2],a[3]) if a[0]=='range' else [self.node_value(a,sheet)]
                    nums.extend(float(v) for v in vals if isinstance(v,(int,float)) and not isinstance(v,bool))
                else:
                    v=self.node_value(a,sheet)
                    if name=='COUNT':
                        try:nums.append(num(v))
                        except FormulaError:pass
                    else:nums.append(num(v))
            if name == "COUNT":
                return float(len(nums))
            if name == "MAX":
                return max(nums) if nums else 0
            if name == "MIN":
                return min(nums) if nums else 0
            return sum(nums)

        vals = [self.node_value(a, sheet) for a in args]

        if name == "IF":
            cond = vals[0]
            return vals[1] if truthy(cond) else (vals[2] if len(vals) > 2 else False)
        if name == "AND":
            return all(truthy(v) for v in vals)
        if name == "OR":
            return any(truthy(v) for v in vals)
        if name == "NOT":
            return not truthy(vals[0])
        if name == "SQRT":
            return math.sqrt(num(vals[0]))
        if name == "ABS":
            return abs(num(vals[0]))
        if name == "SIN":
            return math.sin(num(vals[0]))
        if name == "COS":
            return math.cos(num(vals[0]))
        if name == "ROUND":
            digits = int(num(vals[1])) if len(vals) > 1 else 0
            return float(Decimal(str(num(vals[0]))).quantize(Decimal(1).scaleb(-digits),rounding=ROUND_HALF_UP))
        if name == "INT":
            return math.floor(num(vals[0]))
        if name == 'CEILING.MATH':
            sig=abs(num(vals[1])) if len(vals)>1 else 1
            x=num(vals[0]);mode=num(vals[2]) if len(vals)>2 else 0
            if sig==0:return 0
            return (math.floor(x/sig) if x<0 and mode!=0 else math.ceil(x/sig))*sig
        if name == "CEILING":
            sig = num(vals[1]) if len(vals) > 1 else 1
            if sig == 0:
                return 0
            if num(vals[0])>0 and sig<0:raise FormulaError('CEILING significance sign invalid')
            return math.ceil(num(vals[0]) / sig) * sig
        if name == "FLOOR":
            sig = num(vals[1]) if len(vals) > 1 else 1
            if sig == 0:raise FormulaError('FLOOR significance is zero')
            if num(vals[0])>0 and sig<0:raise FormulaError('FLOOR significance sign invalid')
            return math.floor(num(vals[0]) / sig) * sig
        raise FormulaError(f"unsupported function {name}")


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def num(v):
    if v is None or is_blank(v):
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v))
    except ValueError:
        raise FormulaError(f'non-numeric value used in arithmetic: {v!r}')


def text(v):
    if v is None or is_blank(v):
        return ""
    return str(v)


def truthy(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.upper() in ('TRUE','FALSE'):return v.upper()=='TRUE'
        raise FormulaError('text used as logical condition')
    return num(v) != 0


def cmp_eq(a, b):
    return abs(a - b) < 1e-12


def l(v):  # normalise for concatenation
    return v
