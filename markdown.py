import re
from typing import Dict, Iterable, Iterator, List, Union

from .apidoc import LuaFunc
from .util import Command

MD_TITLE_PAT = re.compile(r"^#(#+) (.+)$", re.MULTILINE)
MD_BOLD_PAT = re.compile(r"\*\*([^\*]+)\*\*")
MD_LINK_PAT = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")
MD_LINE_BREAK_PAT = re.compile(r"\s*\\$")


__all__ = [
    "generate_md_toc",
    "create_md_anchor",
    "markdown_paragraph",
    "format_md_table_row",
    "format_md_table",
    "format_md_commands",
    "render_md_api",
]


def file_iter(filename: str) -> Iterator[str]:
    with open(filename, "r", encoding="utf-8") as ifile:
        yield from ifile


def generate_md_toc(
    filename_or_lines: Union[str, List[str]], max_level: int = 99
) -> List[str]:
    ret = []
    lines: Iterable[str] = []
    if isinstance(filename_or_lines, str):
        lines = file_iter(filename_or_lines)
    else:
        lines = filename_or_lines
    for line in lines:
        m = MD_TITLE_PAT.match(line)
        if m:
            level = len(m[1]) - 1
            if level < max_level:
                prefix = "  " * level
                title_link = create_md_anchor(m[2])
                link = f"[{m[2]}](#{title_link})"
                ret.append(prefix + "- " + link + "\n")
    return ret


def create_md_anchor(title: str) -> str:
    title = re.sub(r"\s", "-", title.lower())
    title = re.sub(r"[^\w\-]", "", title.lower())
    return title


def markdown_paragraph(block: str) -> List[str]:
    return [" \\\n".join(block.rstrip().split("\n")) + "\n"]


def format_md_table_row(
    data: Dict, column_names: List[str], max_widths: Dict[str, int]
) -> str:
    cols = []
    for col in column_names:
        cols.append(data.get(col, "").ljust(max_widths[col]))
    return "| " + " | ".join(cols) + " |\n"


def format_md_table(rows: List[Dict], column_names: List[str]) -> List[str]:
    max_widths: Dict[str, int] = {col: max(3, len(col)) for col in column_names}
    for row in rows:
        for col in column_names:
            max_widths[col] = max(max_widths[col], len(row.get(col, "")))
    lines = []
    titles = []
    for col in column_names:
        titles.append(col.ljust(max_widths[col]))
    lines.append("| " + " | ".join(titles) + " |\n")
    seps = []
    for col in column_names:
        seps.append(max_widths[col] * "-")
    lines.append("| " + " | ".join(seps) + " |\n")
    for row in rows:
        lines.append(format_md_table_row(row, column_names, max_widths))
    return lines


def format_md_commands(commands: List[Command]) -> List[str]:
    lines = ["\n"]
    rows = []
    for command in commands:
        if command.deprecated:
            continue
        cmd = command.cmd
        if command.defn.count:
            cmd = "[count]" + cmd
        if command.defn.bang:
            cmd += "[!]"
        rows.append(
            {
                "Command": "`" + cmd + "`",
                "Args": command.args,
                "Description": command.defn.desc,
            }
        )
    lines.extend(format_md_table(rows, ["Command", "Args", "Description"]))
    lines.append("\n")
    return lines


def render_md_api(funcs: List[LuaFunc], level: int = 3) -> List[str]:
    lines = []
    for func in funcs:
        if func.private or func.deprecated:
            continue
        args = ", ".join([param.name for param in func.params])
        signature = f"{func.name}({args})"
        lines.append(level * "#" + f" {signature}\n")
        if func.returns:
            signature += ": " + ", ".join([r.type for r in func.returns])
        lines.append("\n")
        lines.append(f"`{signature}`")
        if func.summary:
            lines.append(" \\\n")
            lines.append(func.summary)
            lines.append("\n\n")
        else:
            lines.append("\n\n")
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
        if any([r.desc for r in func.returns]):
            lines.append("\n")
            lines.append("Returns:\n")
            rows = [{"Type": r.type, "Desc": r.desc} for r in func.returns]
            lines.extend(format_md_table(rows, ["Type", "Desc"]))
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
