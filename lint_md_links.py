import itertools
import os
import re
import sys
from functools import lru_cache
from typing import List

from .markdown import MD_LINK_PAT, MD_TITLE_PAT, create_md_anchor


@lru_cache
def read(filename: str) -> str:
    with open(filename, "r", encoding="utf-8") as ifile:
        return ifile.read()


def validate_anchor(filename: str, anchor: str) -> bool:
    text = read(filename)
    for match in re.finditer(MD_TITLE_PAT, text):
        title = match[2]
        link_match = MD_LINK_PAT.match(title)
        if link_match:
            title = link_match[1]
        if anchor == create_md_anchor(title):
            return True
    return False


def lint_file(filename: str, root: str) -> List[str]:
    errors = []
    text = read(filename)

    inside_code_block = False

    inside_code_block = False
    with open(filename, "r", encoding="utf-8") as ifile:
        for line in ifile:
            if inside_code_block:
                inside_code_block = not re.match(r"^```", line)
                continue
            elif re.match(r"^```", line):
                inside_code_block = True
                continue
            for match in re.finditer(MD_LINK_PAT, line):
                link = match[2]
                if re.match(r"^<?http", link):
                    continue
                pieces = link.split("#")
                if len(pieces) == 1:
                    linkfile, anchor = pieces[0], None
                elif len(pieces) == 2:
                    linkfile, anchor = pieces
                else:
                    raise ValueError(f"Invalid link {link}")
                if linkfile:
                    abs_linkfile = os.path.join(os.path.dirname(filename), linkfile)
                else:
                    abs_linkfile = filename

                relfile = os.path.relpath(filename, root)
                if not os.path.exists(abs_linkfile):
                    errors.append(f"{relfile} invalid link: {link}")
                elif anchor and not validate_anchor(abs_linkfile, anchor):
                    errors.append(f"{relfile} invalid link anchor: {link}")

    return errors


def main(root: str, files: List[str]) -> None:
    """Main method"""
    errors = list(
        itertools.chain.from_iterable([lint_file(file, root) for file in files])
    )
    for error in errors:
        print(error)
    sys.exit(len(errors))
