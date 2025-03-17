#!/usr/bin/env python
"""
This script indexes a Python project by generating a file tree, detailed definitions, and dependency listings.
https://github.com/KayumovRu/indexer-py
version: 0.1
"""

import os
import ast
import fnmatch

# Single ignore set for files and directories (patterns ending with "/" indicate directories)
IGNORE = {
    "__pycache__",
    "indexer_data/",
    "venv/",
    "env/",
    "logs/",
    ".*",
    "indexer.py",
    "bot.log",
    "*.md",
    "*.txt",
    "*.csv",
    "*.db",
    "Dockerfile",
    ".yaml",
    ".json"
}

# ---------------------- Utility Functions ---------------------- #
def is_ignored(item, is_dir=False):
    """
    Checks if the given item (file or directory name) matches any pattern in IGNORE.
    For directory patterns, the pattern must end with a "/".
    """
    for pattern in IGNORE:
        if pattern.endswith("/"):
            if is_dir and fnmatch.fnmatch(item + "/", pattern):
                return True
        else:
            if fnmatch.fnmatch(item, pattern):
                return True
    return False

def parse_docstring_sections(docstring):
    """
    Splits a docstring into:
      - Base description (before any section headers)
      - Args lines (after the 'Args:' header)
      - Returns lines (after the 'Returns:' header)
    """
    base_lines, args_lines, returns_lines = [], [], []
    mode = "base"
    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped.startswith("Args:"):
            mode = "Args"
            continue
        elif stripped.startswith("Returns:"):
            mode = "Returns"
            continue
        else:
            if mode == "base":
                base_lines.append(stripped)
            elif mode == "Args" and stripped:
                args_lines.append(stripped)
            elif mode == "Returns" and stripped:
                returns_lines.append(stripped)
    base_doc = " ".join(base_lines).strip()
    return base_doc, args_lines, returns_lines

def extract_preceding_comments(source_lines, start_line):
    """
    Extracts comments immediately preceding the line at start_line.
    """
    comments = []
    idx = start_line - 2  # Convert 1-indexed to 0-indexed; start from the previous line.
    while idx >= 0:
        line = source_lines[idx].rstrip()
        if not line.strip():
            break
        if line.strip().startswith("#"):
            comments.insert(0, line.strip()[1:].strip())
            idx -= 1
        else:
            break
    return " ".join(comments).strip()

# ---------------------- AST Parsing Functions ---------------------- #
def extract_entities(nodes, source_lines):
    """
    Recursively extracts entities (functions, async functions, classes) from AST nodes.
    Each entity is represented as (Type, Name, Annotation, Children).
    For functions, any 'Args:' or 'Returns:' sections in the docstring are added as child nodes.
    """
    entities = []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start_line = node.lineno
            if node.decorator_list:
                deco_lines = [d.lineno for d in node.decorator_list]
                start_line = min(start_line, min(deco_lines))
            comment_block = extract_preceding_comments(source_lines, start_line)
            docstring = ast.get_docstring(node) or ""
            base_doc, args_list, returns_list = parse_docstring_sections(docstring)
            annotation = (comment_block + " | " + base_doc) if comment_block and base_doc else (comment_block or base_doc)
            etype = "Async Function" if isinstance(node, ast.AsyncFunctionDef) else "Function"
            body_entities = extract_entities(node.body, source_lines)
            extra_children = []
            if args_list:
                extra_children.append(("Args", "", "\n".join(args_list), []))
            if returns_list:
                extra_children.append(("Returns", "", "\n".join(returns_list), []))
            entities.append((etype, node.name, annotation, extra_children + body_entities))
        elif isinstance(node, ast.ClassDef):
            start_line = node.lineno
            if node.decorator_list:
                deco_lines = [d.lineno for d in node.decorator_list]
                start_line = min(start_line, min(deco_lines))
            comment_block = extract_preceding_comments(source_lines, start_line)
            docstring = ast.get_docstring(node) or ""
            annotation = (comment_block + " | " + docstring) if comment_block and docstring else (comment_block or docstring)
            children = extract_entities(node.body, source_lines)
            entities.append(("Class", node.name, annotation, children))
    return entities

def parse_py_file(filepath):
    """
    Parses a Python file to extract its module-level docstring and entities.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception:
        return "", []
    source_lines = source.splitlines()
    try:
        node = ast.parse(source, filepath)
    except Exception:
        return "", []
    mod_doc = ast.get_docstring(node) or ""
    entities = extract_entities(node.body, source_lines)
    return mod_doc, entities

def format_entity_tree(entities, prefix=""):
    """
    Recursively formats entities into a tree structure with branch connectors.
    For 'Args' and 'Returns' nodes, multi-line annotations are split into child lines.
    """
    lines = []
    count = len(entities)
    for idx, (etype, name, annotation, children) in enumerate(entities):
        is_last = (idx == count - 1)
        connector = "└── " if is_last else "├── "
        line = prefix + connector + f"[{etype}] {name}"
        if annotation and etype not in ("Args", "Returns"):
            line += f"  # {annotation}"
        lines.append(line)
        if etype in ("Args", "Returns") and annotation:
            ann_lines = annotation.split("\n")
            ann_count = len(ann_lines)
            new_prefix = prefix + ("    " if is_last else "│   ")
            for i, ann_line in enumerate(ann_lines):
                ann_connector = "└── " if i == ann_count - 1 else "├── "
                lines.append(new_prefix + ann_connector + ann_line)
        if children:
            new_prefix = prefix + ("    " if is_last else "│   ")
            lines.extend(format_entity_tree(children, new_prefix))
    return lines

# ---------------------- File Tree & Definitions ---------------------- #
def build_tree_files(start_path, prefix=""):
    """
    Builds a tree representation of the project structure.
    For Python files, appends the module-level docstring (if any).
    Items matching IGNORE are marked as 'ignored' and not processed further.
    """
    lines = []
    try:
        entries = sorted(e for e in os.listdir(start_path) if not e.startswith('.'))
    except Exception:
        return lines
    for i, entry in enumerate(entries):
        full_path = os.path.join(start_path, entry)
        connector = "└── " if i == len(entries) - 1 else "├── "
        if os.path.isdir(full_path):
            if is_ignored(entry, is_dir=True):
                lines.append(prefix + connector + entry + "/  # ignored")
            else:
                lines.append(prefix + connector + entry + "/")
                new_prefix = prefix + ("    " if i == len(entries) - 1 else "│   ")
                lines.extend(build_tree_files(full_path, new_prefix))
        else:
            if is_ignored(entry, is_dir=False):
                lines.append(prefix + connector + entry + "  # ignored")
            else:
                if entry.endswith(".py"):
                    mod_doc, _ = parse_py_file(full_path)
                    comment = f"  # {mod_doc}" if mod_doc else ""
                    lines.append(prefix + connector + entry + comment)
                else:
                    lines.append(prefix + connector + entry)
    return lines

def build_map_definitions(start_path, prefix=""):
    """
    Builds a tree of detailed definitions (functions, classes, nested entities)
    for each Python file in the project.
    Items matching IGNORE are marked as 'ignored' and not processed.
    Output is intended for 'map_definitions.txt'.
    """
    lines = []
    try:
        entries = sorted(e for e in os.listdir(start_path) if not e.startswith('.'))
    except Exception:
        return lines
    for i, entry in enumerate(entries):
        full_path = os.path.join(start_path, entry)
        connector = "└── " if i == len(entries) - 1 else "├── "
        if os.path.isdir(full_path):
            if is_ignored(entry, is_dir=True):
                lines.append(prefix + connector + entry + "/  # ignored")
            else:
                lines.append(prefix + connector + entry + "/")
                new_prefix = prefix + ("    " if i == len(entries) - 1 else "│   ")
                lines.extend(build_map_definitions(full_path, new_prefix))
        else:
            if is_ignored(entry, is_dir=False):
                lines.append(prefix + connector + entry + "  # ignored")
            else:
                if entry.endswith(".py"):
                    mod_doc, entities = parse_py_file(full_path)
                    comment = f"  # {mod_doc}" if mod_doc else ""
                    lines.append(prefix + connector + entry + comment)
                    new_prefix = prefix + ("    " if i == len(entries) - 1 else "│   ") + "    "
                    if entities:
                        lines.extend(format_entity_tree(entities, new_prefix))
    return lines

# ---------------------- Dependency Helpers ---------------------- #
def get_full_name(node):
    """
    Reconstructs the full name of a called function/class from an AST node.
    """
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        prefix = get_full_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""

def get_used_entities(filepath):
    """
    Analyzes a Python file and returns:
      (set of imported modules, set of called functions/classes)
    """
    imports, calls = set(), set()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception:
        return imports, calls
    try:
        node = ast.parse(source, filepath)
    except Exception:
        return imports, calls
    for n in ast.walk(node):
        if isinstance(n, ast.Import):
            for alias in n.names:
                imports.add(alias.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                imports.add(n.module)
        elif isinstance(n, ast.Call):
            name = get_full_name(n.func)
            if name:
                calls.add(name)
    return imports, calls

def build_local_modules(start_path):
    """
    Scans the project for Python files and builds a mapping from fully qualified module names
    to their relative file paths.
    For a file at 'pkg/subpkg/module.py', the module name is assumed to be 'pkg.subpkg.module'.
    For __init__.py files, the module name is the package name.
    Items matching IGNORE are skipped.
    """
    local_modules = {}
    for root, dirs, files in os.walk(start_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not is_ignored(d, is_dir=True)]
        for file in files:
            if file.endswith(".py") and not is_ignored(file, is_dir=False):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, start_path)
                parts = rel_path.split(os.sep)
                if parts[-1] == "__init__.py":
                    mod_name = ".".join(parts[:-1])
                else:
                    mod_name = ".".join(parts)[:-3]  # remove .py extension
                local_modules[mod_name] = rel_path
    return local_modules

def build_dependencies(start_path):
    """
    Builds dependencies for each Python file by listing imported modules and used functions/classes.
    The output starts with a section listing all external libraries (top-level names)
    excluding those corresponding to local modules.
    Items matching IGNORE are skipped.
    """
    all_imports = set()
    file_deps = []
    for root, dirs, files in os.walk(start_path):
        dirs[:] = [d for d in dirs if not is_ignored(d, is_dir=True)]
        for file in files:
            if file.endswith(".py") and not is_ignored(file, is_dir=False):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, start_path)
                imports, calls = get_used_entities(full_path)
                all_imports.update(imports)
                file_deps.append((rel_path, imports, calls))
    local_modules = build_local_modules(start_path)
    external_libs = set()
    for mod in all_imports:
        top_level = mod.split('.')[0]
        if top_level not in local_modules:
            external_libs.add(top_level)
    external_libs = sorted(external_libs)
    
    lines = []
    lines.append("Project External Libraries:")
    for lib in external_libs:
        lines.append(f"  - {lib}")
    lines.append("")
    for rel_path, imports, calls in file_deps:
        lines.append(f"File: {rel_path}")
        if imports:
            lines.append("  Imported Modules:")
            for mod in sorted(imports):
                lines.append(f"    - {mod}")
        if calls:
            lines.append("  Used Functions/Classes:")
            for call in sorted(calls):
                lines.append(f"    - {call}")
        lines.append("")
    return lines

# ---------------------- Statistics ---------------------- #
def build_stats(start_path):
    """
    Computes project statistics:
      - Number of directories
      - Number of files (excluding ignored items)
      - Total number of lines (excluding ignored items)
      - Total number of bytes (excluding ignored items)
    """
    dirs_count = files_count = lines_count = bytes_count = 0
    for root, dirs, files in os.walk(start_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not is_ignored(d, is_dir=True)]
        for d in dirs:
            dirs_count += 1
        for file in files:
            if is_ignored(file, is_dir=False):
                continue
            files_count += 1
            full_path = os.path.join(root, file)
            try:
                bytes_count += os.path.getsize(full_path)
            except Exception:
                pass
            try:
                with open(full_path, "rb") as f:
                    lines_count += sum(1 for _ in f)
            except Exception:
                pass
    return dirs_count, files_count, lines_count, bytes_count

# ---------------------- File Writing ---------------------- #
def write_file(filepath, header, lines):
    """
    Writes the header and content lines to a file.
    """
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + "\n\n")
        f.write("\n".join(lines))

# ---------------------- Main ---------------------- #
if __name__ == "__main__":
    start_dir = os.getcwd()
    os.makedirs("indexer_data", exist_ok=True)

    # Headers for output files (in English)
    dependencies_header = (
        "# dependencies.txt\n"
        "# Description: Contains the project's dependencies.\n"
        "# The first section lists all external libraries imported in the project (excluding local modules).\n"
        "# Following sections list, per file, the imported modules and used functions/classes.\n"
        "# Usage: Open this file to view the project's dependencies."
    )
    tree_files_header = (
        "# tree_files.txt\n"
        "# Description: Represents the directory and file structure of the project.\n"
        "# For Python files, the module-level docstring (if available) is appended as a comment.\n"
        "# Items matching IGNORE are marked as 'ignored'.\n"
        "# Usage: Open this file to review the project's file hierarchy."
    )
    map_definitions_header = (
        "# map_definitions.txt\n"
        "# Description: Contains detailed definitions of all entities (functions, classes, and nested definitions) in each Python file.\n"
        "# Items matching IGNORE are marked as 'ignored' and are not processed for definitions.\n"
        "# Note: 'Args' and 'Returns' sections are nested under the corresponding function.\n"
        "# Usage: Open this file to inspect the project's internal definitions."
    )
    stat_header = (
        "# stat.txt\n"
        "# Description: Provides statistics about the project.\n"
        "# Includes counts of directories, files (excluding ignored items), lines, and bytes.\n"
        "# Usage: Open this file to see the project's overall statistics."
    )

    # Build output sections
    tree_files_lines = build_tree_files(start_dir)
    map_definitions_lines = build_map_definitions(start_dir)
    dependencies_lines = build_dependencies(start_dir)
    dirs_count, files_count, lines_count, bytes_count = build_stats(start_dir)
    stat_lines = [
        f"Number of directories: {dirs_count}",
        f"Number of files: {files_count}",
        f"Total number of lines: {lines_count}",
        f"Total number of bytes: {bytes_count}"
    ]

    # Write output files into the 'indexer_data' directory.
    write_file(os.path.join("indexer_data", "dependencies.txt"), dependencies_header, dependencies_lines)
    write_file(os.path.join("indexer_data", "tree_files.txt"), tree_files_header, tree_files_lines)
    write_file(os.path.join("indexer_data", "map_definitions.txt"), map_definitions_header, map_definitions_lines)
    write_file(os.path.join("indexer_data", "stat.txt"), stat_header, stat_lines)

    # Print completion message with statistics to terminal.
    print("Indexing complete.")
    print(f"Number of directories: {dirs_count}")
    print(f"Number of files: {files_count}")
    print(f"Total number of lines: {lines_count}")
