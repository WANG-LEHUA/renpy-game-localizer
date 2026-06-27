#!/usr/bin/env python
"""Extract empty Ren'Py translation templates from compiled .rpyc files.

This script is intentionally Python 2 compatible for older Ren'Py 7 games.
Run it with the game's bundled Python when normal Python 3 cannot unpickle
Ren'Py AST objects, for example:

  <game>/lib/windows-i686/python.exe -O -S extract_rpyc_translations.py \
      --project-root <game> --input-root <game>/game --output-root <out> \
      --language schinese
"""

from __future__ import print_function

import argparse
import io
import json
import os
import struct
import sys
import zlib

try:
    import cPickle as pickle
except ImportError:
    import pickle

try:
    unicode
except NameError:
    unicode = str


RPYC2_HEADER = b"RENPY RPC2"


def bootstrap_paths_from_argv():
    if "--project-root" not in sys.argv:
        return None
    index = sys.argv.index("--project-root")
    if index + 1 >= len(sys.argv):
        return None
    project_root = sys.argv[index + 1]
    for item in reversed((
        project_root,
        os.path.join(project_root, "lib", "windows-i686", "Lib"),
        os.path.join(project_root, "lib", "pythonlib2.7"),
    )):
        if item not in sys.path:
            sys.path.insert(0, item)
    return project_root


bootstrap_paths_from_argv()


def setup_renpy(project_root):
    for item in reversed((
        project_root,
        os.path.join(project_root, "lib", "windows-i686", "Lib"),
        os.path.join(project_root, "lib", "pythonlib2.7"),
    )):
        if item not in sys.path:
            sys.path.insert(0, item)

    import renpy

    renpy_roots = [
        os.path.join(project_root, "renpy"),
        os.path.join(project_root, "lib", "windows-i686", "Lib", "renpy"),
    ]
    for renpy_lib in renpy_roots:
        if os.path.isdir(renpy_lib) and renpy_lib not in renpy.__path__:
            renpy.__path__.append(renpy_lib)
    for package_name, rel_path in (
        ("renpy.display", "display"),
        ("renpy.text", "text"),
        ("renpy.styledata", "styledata"),
        ("renpy.gl", "gl"),
        ("renpy.angle", "angle"),
    ):
        try:
            package = __import__(package_name, fromlist=["dummy"])
            for renpy_lib in renpy_roots:
                package_path = os.path.join(renpy_lib, rel_path)
                if os.path.isdir(package_path) and package_path not in package.__path__:
                    package.__path__.append(package_path)
        except Exception:
            pass
    import renpy.object  # noqa: F401

    class DummyScript(object):
        all_pyexpr = None
        record_pycode = False
        all_pycode = []

    class DummyLog(object):
        mutated = {}

    class DummyGame(object):
        script = DummyScript()
        log = DummyLog()

    renpy.game = DummyGame()
    import renpy.ast  # noqa: F401


def as_text(value):
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    try:
        return unicode(value, "utf-8", "replace")
    except TypeError:
        return unicode(value)


def read_rpyc_slot(path, slot):
    with open(path, "rb") as handle:
        header = handle.read(1024)
        if header[: len(RPYC2_HEADER)] != RPYC2_HEADER:
            if slot != 1:
                return None
            handle.seek(0)
            return zlib.decompress(handle.read())

        pos = len(RPYC2_HEADER)
        while True:
            header_slot, start, length = struct.unpack("III", header[pos : pos + 12])
            if header_slot == slot:
                handle.seek(start)
                return zlib.decompress(handle.read(length))
            if header_slot == 0:
                return None
            pos += 12


def load_statements(path):
    for slot in (2, 1):
        payload = read_rpyc_slot(path, slot)
        if not payload:
            continue
        _, statements = pickle.loads(payload)
        return statements
    raise RuntimeError("Could not load {}".format(path))


def walk_nodes(nodes):
    for node in nodes:
        yield node
        block = getattr(node, "block", None)
        if isinstance(block, list):
            for child in walk_nodes(block):
                yield child
        else_block = getattr(node, "else_", None)
        if isinstance(else_block, list):
            for child in walk_nodes(else_block):
                yield child
        if node.__class__.__name__ == "Menu":
            for item in getattr(node, "items", []):
                if len(item) >= 3 and isinstance(item[2], list):
                    for child in walk_nodes(item[2]):
                        yield child
        elif node.__class__.__name__ == "If":
            for entry in getattr(node, "entries", []):
                if len(entry) >= 2 and isinstance(entry[1], list):
                    for child in walk_nodes(entry[1]):
                        yield child


def quote_renpy(text):
    text = as_text(text)
    text = text.replace(u"\\", u"\\\\")
    text = text.replace(u"\n", u"\\n")
    text = text.replace(u'"', u'\\"')
    return u'"{}"'.format(text)


def say_line(node, empty=False):
    who = getattr(node, "who", None)
    text = u"" if empty else getattr(node, "what", u"")
    prefix = u""
    if who:
        prefix = as_text(who) + u" "
    return prefix + quote_renpy(text)


def source_file_for(node):
    return as_text(getattr(node, "filename", u"")).replace(u"\\", u"/")


def rel_output_path(source_file):
    path = source_file[5:] if source_file.startswith(u"game/") else source_file
    if path.endswith(u".rpy"):
        return path
    return path + u".rpy"


def collect_from_file(path):
    statements = load_statements(path)
    translates_by_file = {}
    strings_by_file = {}

    for node in walk_nodes(statements):
        name = node.__class__.__name__
        if name == "Translate" and getattr(node, "language", None) is None:
            block = getattr(node, "block", [])
            if block and all(child.__class__.__name__ == "Say" for child in block):
                source_file = source_file_for(node)
                translates_by_file.setdefault(source_file, []).append(node)
        elif name == "Menu":
            source_file = source_file_for(node)
            for item in getattr(node, "items", []):
                if item and item[0]:
                    strings_by_file.setdefault(source_file, []).append(
                        (getattr(node, "linenumber", 0), item[0])
                    )

    return translates_by_file, strings_by_file


def write_translation_files(out_root, language, all_translates, all_strings):
    written = []
    for source_file in sorted(set(all_translates) | set(all_strings)):
        out_path = os.path.join(out_root, rel_output_path(source_file))
        parent = os.path.dirname(out_path)
        if parent and not os.path.exists(parent):
            os.makedirs(parent)

        with io.open(out_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(u"# Generated from compiled Ren'Py script.\n\n")
            for trans in all_translates.get(source_file, []):
                identifier = as_text(getattr(trans, "identifier", u"")).replace(u".", u"_")
                handle.write(u"# {}:{}\n".format(source_file, getattr(trans, "linenumber", 0)))
                handle.write(u"translate {} {}:\n\n".format(language, identifier))
                for child in trans.block:
                    handle.write(u"    # {}\n".format(say_line(child, empty=False)))
                    handle.write(u"    {}\n".format(say_line(child, empty=True)))
                handle.write(u"\n")

            strings = all_strings.get(source_file, [])
            if strings:
                seen = set()
                handle.write(u"translate {} strings:\n\n".format(language))
                for line, text in strings:
                    key = as_text(text)
                    if key in seen:
                        continue
                    seen.add(key)
                    handle.write(u"    # {}:{}\n".format(source_file, line))
                    handle.write(u"    old {}\n".format(quote_renpy(text)))
                    handle.write(u"    new \"\"\n\n")
        written.append(out_path)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--language", default="schinese")
    parser.add_argument("--stats-json")
    args = parser.parse_args()

    setup_renpy(args.project_root)

    all_translates = {}
    all_strings = {}
    files = []
    skipped = []
    for dirpath, _, filenames in os.walk(args.input_root):
        for filename in filenames:
            if filename.lower().endswith(".rpyc"):
                files.append(os.path.join(dirpath, filename))

    for path in sorted(files):
        try:
            translates, strings = collect_from_file(path)
        except Exception as exc:
            skipped.append({"file": path, "error": repr(exc)})
            continue
        for source_file, items in translates.items():
            all_translates.setdefault(source_file, []).extend(items)
        for source_file, items in strings.items():
            all_strings.setdefault(source_file, []).extend(items)

    written = write_translation_files(args.output_root, args.language, all_translates, all_strings)
    stats = {
        "rpyc_files": len(files),
        "output_files": len(written),
        "translate_blocks": sum(len(value) for value in all_translates.values()),
        "menu_strings": sum(len(value) for value in all_strings.values()),
        "source_files": len(set(all_translates) | set(all_strings)),
        "skipped_files": skipped,
        "skipped_count": len(skipped),
    }
    print(json.dumps(stats, ensure_ascii=False, sort_keys=True))

    if args.stats_json:
        with io.open(args.stats_json, "w", encoding="utf-8") as handle:
            handle.write(as_text(json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=2)))
            handle.write(u"\n")


if __name__ == "__main__":
    main()
