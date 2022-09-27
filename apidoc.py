import os
import re
from dataclasses import dataclass, field
from typing import List

from pyparsing.exceptions import ParseException
from pyparsing import (
    Forward,
    Keyword,
    LineEnd,
    LineStart,
    OneOrMore,
    Opt,
    ParserElement,
    QuotedString,
    Regex,
    Suppress,
    White,
    Word,
    ZeroOrMore,
    alphanums,
    alphas,
    delimitedList,
)

from .util import format_md_table, indent, leftright, wrap

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, os.path.pardir))
DOC = os.path.join(ROOT, "doc")

FN_RE = re.compile(r"^M\.(\w+)\s*=")


@dataclass
class LuaFunc:
    name: str
    summary: str = ""
    params: List["LuaParam"] = field(default_factory=list)
    returns: List["LuaReturn"] = field(default_factory=list)
    example: str = ""
    note: str = ""
    private: bool = False
    deprecated: bool = False

    @classmethod
    def parse_annotation(cls, name: str, lines: List[str]) -> "LuaFunc":
        # Strip off the leading comment
        lines = [line[3:] for line in lines]
        try:
            p = annotation.parseString("".join(lines), parseAll=True)
        except ParseException as e:
            raise Exception(f"Error parsing {name}") from e
        params = []
        returns = []
        for item in p.asList():
            if isinstance(item, LuaParam):
                params.append(item)
            elif isinstance(item, LuaReturn):
                returns.append(item)
        return cls(
            name,
            summary=p.get("summary", ""),
            private="private" in p,
            deprecated="deprecated" in p,
            example=p.get("example", ""),
            note=p.get("note", ""),
            params=params,
            returns=returns,
        )


@dataclass
class LuaParam:
    name: str
    type: str
    desc: str = ""
    subparams: List["LuaParam"] = field(default_factory=list)

    @classmethod
    def from_parser(cls, p):
        sp = p["subparams"].asList() if "subparams" in p else []
        return cls(
            p["name"],
            p["type"],
            desc=p.get("desc", ""),
            subparams=sp,
        )


@dataclass
class LuaReturn:
    type: str
    desc: str = ""

    @classmethod
    def from_parser(cls, p):
        name, *desc = p.asList()
        return cls(name, "".join(desc))


ParserElement.setDefaultWhitespaceChars(" \t")

varname = Word(alphas, alphanums + "_")
lua_type = Forward()
primitive_type = (
    Keyword("nil")
    | Keyword("string")
    | Keyword("integer")
    | Keyword("boolean")
    | Keyword("number")
    | Keyword("table")
    | QuotedString('"', unquote_results=False)
    | Keyword("any")
    | Regex(r"\w+\.[\w]+(\[\])?")
)
lua_list = (
    Keyword("string[]")
    | Keyword("integer[]")
    | Keyword("number[]")
    | Keyword("any[]")
    | Keyword("boolean[]")
)
lua_table = (
    Keyword("table") + "<" + lua_type + "," + Opt(White()) + lua_type + ">"
).setParseAction(lambda p: "".join(p.asList()))
lua_func_param = (
    Opt(White()) + varname + ":" + Opt(White()) + lua_type + Opt(White())
).setParseAction(lambda p: "".join(p.asList()))
lua_func = (
    Keyword("fun")
    + "("
    + Opt(delimitedList(lua_func_param, combine=True))
    + ")"
    + Opt((":") + Opt(White()) + lua_type)
).setParseAction(lambda p: "".join(p.asList()))
non_union_types = lua_list | lua_table | lua_func | primitive_type
union_type = delimitedList(non_union_types, delim="|").setParseAction(
    lambda p: "|".join(p.asList())
)
lua_type <<= union_type | non_union_types

tag = Forward()
subparam = (
    Suppress(LineStart())
    + Suppress(White())
    + varname.setResultsName("name")
    + lua_type.setResultsName("type")
    + Opt(Regex(".+").setResultsName("desc"))
    + Suppress(LineEnd())
).setParseAction(LuaParam.from_parser)
tag_param = (
    Suppress("@param")
    + varname.setResultsName("name")
    + lua_type.setResultsName("type")
    + Opt(Regex(".+").setResultsName("desc"))
    + Suppress(LineEnd())
    + ZeroOrMore(subparam).setResultsName("subparams")
).setParseAction(LuaParam.from_parser)
tag_private = (Keyword("@private") + Suppress(LineEnd())).setResultsName("private")
tag_deprecated = (Keyword("@deprecated") + Suppress(LineEnd())).setResultsName(
    "deprecated"
)

tag_example = (
    (
        Suppress("@example" + LineEnd())
        + OneOrMore(
            LineStart()
            + Suppress(White(max=1))
            + Opt(White())
            + Regex(r".+")
            + LineEnd()
        )
    )
    .setResultsName("example")
    .setParseAction(lambda p: "".join(p.asList()))
)
tag_note = (
    (
        Suppress("@note" + LineEnd())
        + OneOrMore(
            LineStart()
            + Suppress(White(max=1))
            + Opt(White())
            + Regex(r".+")
            + LineEnd()
        )
    )
    .setResultsName("note")
    .setParseAction(lambda p: "".join(p.asList()))
)
tag_return = (
    Suppress("@return")
    + lua_type
    + Opt(Regex(".+").setName("desc"))
    + Suppress(LineEnd())
).setParseAction(LuaReturn.from_parser)
summary = Regex(r"^[^@].+").setResultsName("summary") + Suppress(LineEnd())

tag <<= tag_param | tag_private | tag_return | tag_example | tag_note | tag_deprecated

annotation = Opt(summary) + ZeroOrMore(tag) + Suppress(ZeroOrMore(White()))


def parse_functions(filename: str) -> List[LuaFunc]:
    funcs = []

    with open(filename, "r", encoding="utf-8") as ifile:
        chunk = []
        for line in ifile:
            if line.startswith("---"):
                chunk.append(line)
            elif chunk:
                m = FN_RE.match(line)
                if m:
                    func = LuaFunc.parse_annotation(m[1], chunk)
                    if func is not None:
                        funcs.append(func)
                chunk = []
    return funcs


def render_api_md(funcs: List[LuaFunc]) -> List[str]:
    lines = []
    for func in funcs:
        if func.private or func.deprecated:
            continue
        args = ", ".join([param.name for param in func.params])
        lines.append(f"### {func.name}({args})\n")
        lines.append("\n")
        lines.append(func.summary)
        lines.append("\n")
        any_subparams = False
        if func.params:
            rows = []
            for param in func.params:
                ftype = param.type.replace("|", r"\|")
                rows.append(
                    {
                        "Param": param.name,
                        "Type": f"`{ftype}`",
                        "Desc": param.desc,
                    }
                )
                for subp in param.subparams:
                    any_subparams = True
                    ftype = subp.type.replace("|", r"\|")
                    rows.append(
                        {
                            "Type": subp.name,
                            "Desc": f"`{ftype}`",
                            "": subp.desc,
                        }
                    )

            cols = ["Param", "Type", "Desc"]
            if any_subparams:
                cols.append("")
            lines.extend(format_md_table(rows, cols))
        if func.note:
            lines.append("\n")
            lines.append("**Note:**\n")
            lines.append("<pre>\n")
            lines.append(func.note)
            lines.append("</pre>\n")
        if func.example:
            lines.append("\n")
            lines.append("**Examples:**\n")
            lines.append("```lua\n")
            lines.append(func.example)
            lines.append("```\n")
        lines.append("\n")
    return lines

def format_returns(returns: List[LuaReturn], indent: int) -> List[str]:
    lines = []
    for r in returns:
        prefix = indent * " "
        line = prefix + f"`{r.type}`" + " "
        sub_indent = min(len(prefix), indent + 2)
        desc = wrap(r.desc, indent=len(line), sub_indent=sub_indent)
        if desc:
            desc[0] = line + desc[0].lstrip()
            lines.extend(desc)
        else:
            lines.append(line.rstrip() + "\n")

    return lines

def format_params(params: List[LuaParam], indent: int) -> List[str]:
    lines = []
    # Ignore params longer than 16 chars. They are outliers and will ruin the formatting
    max_param = max([len(param.name) for param in params if len(param.name) <= 16]) + 1
    for param in params:
        prefix = (
            indent * " "
            + "{"
            + f"{param.name}"
            + "}".ljust(max_param - len(param.name))
            + " "
        )
        line = prefix + f"`{param.type}`" + " "
        sub_indent = min(len(prefix), max_param + indent + 2)
        desc = wrap(param.desc, indent=len(line), sub_indent=sub_indent)
        if desc:
            desc[0] = line + desc[0].lstrip()
            lines.extend(desc)
        else:
            lines.append(line.rstrip() + "\n")
        if param.subparams:
            lines.extend(format_params(param.subparams, 10))

    return lines


def render_api_vimdoc(project: str, funcs: List[LuaFunc]) -> List[str]:
    lines = []
    for func in funcs:
        if func.private or func.deprecated:
            continue
        args = ", ".join(["{" + param.name + "}" for param in func.params])
        signature = f"{func.name}({args})"
        if func.returns:
            signature += ': ' + ', '.join([r.type for r in func.returns])
        lines.append(leftright(signature, f"*{project}.{func.name}*"))
        lines.extend(wrap(func.summary, 4))
        lines.append("\n")
        if func.params:
            lines.append(4 * " " + "Parameters:\n")
            lines.extend(format_params(func.params, 6))

        if any([r.desc for r in func.returns]):
            lines.append(4 * " " + "Returns:\n")
            lines.extend(format_returns(func.returns, 6))

        if func.note:
            lines.append("\n")
            lines.append(4 * " " + "Note:\n")
            lines.extend(indent(func.note.splitlines(), 6))
        if func.example:
            lines.append("\n")
            lines.append(4 * " " + "Examples: >\n")
            lines.extend(indent(func.example.splitlines(), 6))
            lines.append("<\n")
        lines.append("\n")
    return lines
