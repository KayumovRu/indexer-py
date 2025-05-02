#!/usr/bin/env python
"""
This script indexes a Python project by generating a file tree, detailed definitions, and dependency listings.
https://github.com/KayumovRu/indexer-py
"""

import os
import ast
import fnmatch
from pathlib import Path

__version__ = "0.1.9"

# Graph colors
NODE_COLOR = "#0074D9"
NODE_SELECTED_COLOR = "#FF4136"
EDGE_INCOMING_COLOR = "#2ECC40"
EDGE_OUTGOING_COLOR = "#FF4136"

# Directory and file constants
OUTPUT_DIR = "indexer_data"
TREE_FILES = os.path.join(OUTPUT_DIR, "tree_files.txt")
MAP_DEFINITIONS = os.path.join(OUTPUT_DIR, "map_definitions.txt")
DEPENDENCIES = os.path.join(OUTPUT_DIR, "dependencies.txt")
STATS = os.path.join(OUTPUT_DIR, "stat.txt")

# Single ignore set for files and directories (patterns ending with "/" indicate directories)
IGNORE = {
    OUTPUT_DIR + "/",
    "__pycache__/",
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
    ".json",
    "LICENSE",
    "__init__.py"
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

# ---------------------- Graph HTML Generation ---------------------- #
def build_call_graph(start_path):
    """Returns list of nodes and edges for graph"""
    local_modules = build_local_modules(start_path)
    nodes = []
    edges = set()  # используем множество для исключения дублирующихся рёбер
    
    # Добавляем узлы для каждого Python-файла в проекте
    for module, rel_path in local_modules.items():
        nodes.append({'id': rel_path, 'label': rel_path})
    
    # Создаем ребра на основе импортов
    for module, rel_path in local_modules.items():
        full_path = os.path.join(start_path, rel_path)
        imports, _ = get_used_entities(full_path)
        
        for imported in imports:
            # Ищем импортированный модуль среди локальных модулей
            imported_prefix = imported.split('.')[0]
            for local_mod, local_path in local_modules.items():
                if local_mod == imported or local_mod.startswith(imported + '.') or imported.startswith(local_mod + '.'):
                    # Если нашли соответствие, добавляем ребро
                    if rel_path != local_path:  # Исключаем самоссылки
                        edges.add((rel_path, local_path))
                    break
    
    return nodes, list(edges)


def write_graph_html(start_path):
    """Generates an HTML file with an interactive dependency graph"""
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Get nodes and edges for the graph
    nodes, edges = build_call_graph(start_path)
    
    # Collect code for each file
    code_repo = {}
    for node in nodes:
        filepath = os.path.join(start_path, node['id'])
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                code_repo[node['id']] = f.read()
        except Exception:
            code_repo[node['id']] = '# Error reading file'
    
    # Get statistics
    dirs_count, files_count, lines_count, bytes_count = build_stats(start_path)
    
    # Get file tree
    tree_files_lines = build_tree_files(start_path)
    
    # Create JavaScript for graph elements
    elements_js = []
    # Add nodes
    for node in nodes:
        node_id = node['id'].replace('\\', '\\\\')  # Escape backslashes for JavaScript
        node_label = node['label'].replace('\\', '/')  # Use forward slashes for display
        elements_js.append(f"{{ data: {{ id: '{node_id}', label: '{node_label}' }} }}")
    
    # Add edges
    for source, target in edges:
        source_id = source.replace('\\', '\\\\')
        target_id = target.replace('\\', '\\\\')
        elements_js.append(f"{{ data: {{ source: '{source_id}', target: '{target_id}' }} }}")
    
    elements_str = ",\n      ".join(elements_js)
    
    # Create JavaScript for code repository
    code_js = []
    for path, code in code_repo.items():
        # Escape backslashes and quotes in path
        path_escaped = path.replace('\\', '\\\\').replace("'", "\\'")
        # Escape special characters in code
        code_escaped = code.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
        code_js.append(f"'{path_escaped}': `{code_escaped}`")
    
    code_str = ",\n      ".join(code_js)
    
    # Format file tree as HTML
    tree_html = "<ul class='file-tree'>\n"
    current_indent = 0
    
    for line in tree_files_lines:
        line_stripped = line.lstrip()
        indent = len(line) - len(line_stripped)
        
        # Handle nesting level changes
        if indent > current_indent:
            tree_html += "<ul>\n"
        elif indent < current_indent:
            # Close the required number of levels
            for _ in range((current_indent - indent) // 4):
                tree_html += "</ul>\n"
        
        current_indent = indent
        
        # Replace connector symbols with HTML
        clean_line = line_stripped
        if clean_line.startswith("├── "):
            clean_line = clean_line[4:]
        elif clean_line.startswith("└── "):
            clean_line = clean_line[4:]
        elif clean_line.startswith("│   "):
            clean_line = clean_line[4:]
        
        # Check if this is a directory or a file
        is_dir = clean_line.endswith("/") or " # ignored" in clean_line and clean_line.replace(" # ignored", "").endswith("/")
        
        # Check if this item is ignored
        is_ignored = " # ignored" in clean_line
        
        # Create class for item type
        item_class = "dir" if is_dir else "file"
        if is_ignored:
            item_class += " ignored"
        
        # Remove comments for display
        item_name = clean_line.split("  #")[0]
        
        tree_html += f"<li class='{item_class}'>{item_name}</li>\n"
    
    # Close remaining open tags
    for _ in range(current_indent // 4 + 1):
        tree_html += "</ul>\n"
    
    # HTML Template
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Project Explorer</title>
  <script src="https://unpkg.com/cytoscape/dist/cytoscape.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/styles/default.min.css">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/languages/python.min.js"></script>
  <style>
    body {{ 
      margin: 0; 
      padding: 0; 
      font-family: Arial, sans-serif; 
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }}
    
    .header {{ 
      padding: 10px; 
      background: #333; 
      color: white; 
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    
    .header h2 {{
      margin: 0;
    }}
    
    .version {{
      font-size: 0.8em;
      opacity: 0.8;
      margin-left: 5px;
    }}
    
    .stats {{
      display: flex;
      gap: 20px;
    }}
    
    .stat-item {{
      display: flex;
      flex-direction: column;
      align-items: center;
    }}
    
    .stat-value {{
      font-size: 1.2em;
      font-weight: bold;
    }}
    
    .main-container {{
      display: flex;
      flex: 1;
      overflow: hidden;
      position: relative;
    }}
    
    .file-tree-panel {{
      width: 25%;
      min-width: 150px;
      border-right: 1px solid #ccc;
      overflow: auto;
      padding: 10px;
      position: relative;
      flex-shrink: 0;
    }}
    
    .graph-panel {{
      flex: 1;
      position: relative;
      min-width: 200px;
    }}
    
    .code-panel {{
      width: 35%;
      min-width: 150px;
      border-left: 1px solid #ccc;
      overflow: auto;
      display: flex;
      flex-direction: column;
      position: relative;
      flex-shrink: 0;
    }}
    
    .file-tree {{
      list-style-type: none;
      padding-left: 0;
    }}
    
    .file-tree ul {{
      list-style-type: none;
      padding-left: 20px;
    }}
    
    .file-tree li {{
      padding: 3px 0;
      cursor: pointer;
    }}
    
    .file-tree li:hover {{
      background-color: #f0f0f0;
    }}
    
    .file-tree .dir::before {{
      content: "📁 ";
    }}
    
    .file-tree .file::before {{
      content: "📄 ";
    }}
    
    .file-tree .ignored {{
      color: #999;
    }}
    
    .file-tree .selected {{
      font-weight: bold;
      background-color: #e0e0ff;
    }}
    
    #cy {{ 
      width: 100%;
      height: 100%;
    }}
    
    .code-header {{
      padding: 5px 10px;
      background: #f0f0f0;
      border-bottom: 1px solid #ccc;
      font-weight: bold;
    }}
    
    .code-content {{
      padding: 10px;
      flex: 1;
      overflow: auto;
    }}
    
    pre {{
      margin: 0;
      white-space: pre-wrap;
    }}
    
    code {{
      font-family: monospace;
    }}
    
    /* Panel resize styles */
    .resizer {{
      width: 8px;
      background: #eee;
      cursor: col-resize;
      position: absolute;
      top: 0;
      bottom: 0;
      z-index: 10;
    }}
    
    .resizer:hover, .resizer.active {{
      background-color: #ccc;
    }}
    
    .left-resizer {{
      right: 0;
    }}
    
    .right-resizer {{
      left: 0;
    }}
  </style>
</head>
<body>
  <div class="header">
    <h2>Project Explorer <span class="version">(v{__version__})</span></h2>
    <div class="stats">
      <div class="stat-item">
        <div class="stat-value">{dirs_count}</div>
        <div class="stat-label">Directories</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{files_count}</div>
        <div class="stat-label">Files</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{lines_count}</div>
        <div class="stat-label">Lines</div>
      </div>
      <div class="stat-item">
        <div class="stat-value">{bytes_count // 1024} KB</div>
        <div class="stat-label">Size</div>
      </div>
    </div>
  </div>
  
  <div class="main-container" id="main-container">
    <div class="file-tree-panel" id="file-tree-panel">
      <h3>Project Files</h3>
      {tree_html}
      <div class="resizer left-resizer" id="left-resizer"></div>
    </div>
    
    <div class="graph-panel" id="graph-panel">
      <div id="cy"></div>
    </div>
    
    <div class="code-panel" id="code-panel">
      <div class="code-header" id="code-header">Code View</div>
      <div class="code-content" id="code-content">
        <pre><code class="language-python">Click a node to view its code</code></pre>
      </div>
      <div class="resizer right-resizer" id="right-resizer"></div>
    </div>
  </div>
  
  <script>
    // Initialize the graph
    const elements = [
      {elements_str}
    ];
    
    const codeRepo = {{
      {code_str}
    }};
    
    const cy = cytoscape({{
      container: document.getElementById('cy'),
      elements,
      style: [
        {{
          selector: 'node',
          style: {{
            'label': 'data(label)',
            'text-valign': 'center',
            'background-color': '{NODE_COLOR}',
            'color': '#fff',
            'padding': '10px',
            'text-wrap': 'wrap',
            'width': 'label',
            'height': 'label',
            'text-max-width': '120px'
          }}
        }},
        {{
          selector: 'node:selected',
          style: {{
            'background-color': '{NODE_SELECTED_COLOR}',
            'border-width': '2px',
            'border-color': '#000'
          }}
        }},
        {{
          selector: 'edge',
          style: {{
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'line-color': '#ccc',
            'target-arrow-color': '#ccc',
            'width': 2
          }}
        }}
      ],
      layout: {{
        name: 'cose',
        directed: true,
        padding: 30,
        componentSpacing: 40,
        nodeOverlap: 20,
        animate: false
      }}
    }});
    
    // Function to highlight incoming/outgoing edges
    function highlightConnections(nodeId) {{
      // Reset all edges
      cy.edges().style({{
        'line-color': '#ccc',
        'target-arrow-color': '#ccc'
      }});
      
      // Highlight incoming edges (green)
      cy.edges().filter(edge => edge.target().id() === nodeId).style({{
        'line-color': '{EDGE_INCOMING_COLOR}',
        'target-arrow-color': '{EDGE_INCOMING_COLOR}'
      }});
      
      // Highlight outgoing edges (red)
      cy.edges().filter(edge => edge.source().id() === nodeId).style({{
        'line-color': '{EDGE_OUTGOING_COLOR}',
        'target-arrow-color': '{EDGE_OUTGOING_COLOR}'
      }});
    }}
    
    // Function to mark selected file in tree
    function markSelectedFile(filePath) {{
      // Remove previous selection
      document.querySelectorAll('.file-tree .selected').forEach(item => {{
        item.classList.remove('selected');
      }});
      
      // Find and highlight matching items
      document.querySelectorAll('.file-tree li').forEach(item => {{
        const itemText = item.textContent.trim();
        if (filePath.endsWith(itemText)) {{
          item.classList.add('selected');
          
          // Ensure parent lists are expanded
          let parent = item.parentElement;
          while (parent && parent.tagName === 'UL') {{
            parent.style.display = 'block';
            parent = parent.parentElement;
          }}
          
          // Scroll into view if necessary
          item.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
      }});
    }}
    
    // Click handler for nodes
    cy.on('tap', 'node', evt => {{
      const node = evt.target;
      const nodeId = node.id();
      
      // Update code display
      const displayPath = nodeId.replace(/\\\\/g, '/');
      document.getElementById('code-header').textContent = displayPath;
      
      const codeContent = codeRepo[nodeId] || 'Code not available';
      const codePanel = document.getElementById('code-content');
      
      // Set code with syntax highlighting
      codePanel.innerHTML = '<pre><code class="language-python">' + 
        codeContent.replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;') + 
        '</code></pre>';
      
      // Apply syntax highlighting
      document.querySelectorAll('pre code').forEach((block) => {{
        hljs.highlightBlock(block);
      }});
      
      // Highlight connections
      highlightConnections(nodeId);
      
      // Mark selected file in tree
      markSelectedFile(displayPath);
    }});
    
    // Click handler for files in the tree
    document.querySelectorAll('.file-tree .file').forEach(fileItem => {{
      fileItem.addEventListener('click', () => {{
        // Skip if this is an ignored item
        if (fileItem.classList.contains('ignored')) return;
        
        const fileName = fileItem.textContent.trim();
        
        // Find corresponding node in the graph
        cy.nodes().forEach(node => {{
          const nodeLabel = node.data('label');
          if (nodeLabel.endsWith(fileName)) {{
            // Center and select the node
            cy.fit(node, 50);
            node.select();
            
            // Display code and highlight connections
            const nodeId = node.id();
            document.getElementById('code-header').textContent = nodeId.replace(/\\\\/g, '/');
            
            const codeContent = codeRepo[nodeId] || 'Code not available';
            const codePanel = document.getElementById('code-content');
            
            // Set code with syntax highlighting
            codePanel.innerHTML = '<pre><code class="language-python">' + 
              codeContent.replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;') + 
              '</code></pre>';
            
            // Apply syntax highlighting
            document.querySelectorAll('pre code').forEach((block) => {{
              hljs.highlightBlock(block);
            }});
            
            // Highlight connections
            highlightConnections(nodeId);
            
            // Mark as selected
            fileItem.classList.add('selected');
          }}
        }});
      }});
    }});
    
    // Improved panel resizing
    // Track which resizer is being dragged
    let activeResizer = null;
    
    // Left panel resizer (file tree)
    const leftResizer = document.getElementById('left-resizer');
    const fileTreePanel = document.getElementById('file-tree-panel');
    
    leftResizer.addEventListener('mousedown', function(e) {{
      e.preventDefault();
      activeResizer = 'left';
      document.body.style.cursor = 'col-resize';
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      this.classList.add('active');
    }});
    
    // Right panel resizer (code)
    const rightResizer = document.getElementById('right-resizer');
    const codePanel = document.getElementById('code-panel');
    const mainContainer = document.getElementById('main-container');
    
    rightResizer.addEventListener('mousedown', function(e) {{
      e.preventDefault();
      activeResizer = 'right';
      document.body.style.cursor = 'col-resize';
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      this.classList.add('active');
    }});
    
    function handleMouseMove(e) {{
      if (!activeResizer) return;
      
      const containerWidth = mainContainer.offsetWidth;
      
      if (activeResizer === 'left') {{
        // Left panel resizing
        const position = (e.clientX / containerWidth) * 100;
        // Enforce min/max size
        if (position > 5 && position < 50) {{
          fileTreePanel.style.width = position + '%';
        }}
      }} else if (activeResizer === 'right') {{
        // Right panel resizing
        const position = ((containerWidth - e.clientX) / containerWidth) * 100;
        // Enforce min/max size
        if (position > 5 && position < 50) {{
          codePanel.style.width = position + '%';
        }}
      }}
      
      // Ensure Cytoscape graph redraws correctly
      cy.resize();
    }}
    
    function handleMouseUp() {{
      activeResizer = null;
      document.body.style.cursor = '';
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      leftResizer.classList.remove('active');
      rightResizer.classList.remove('active');
    }}
    
    // Initialize highlight.js for all code blocks
    document.addEventListener('DOMContentLoaded', () => {{
      document.querySelectorAll('pre code').forEach((block) => {{
        hljs.highlightBlock(block);
      }});
    }});
  </script>
</body>
</html>"""
    
    # Write HTML to file
    graph_path = os.path.join(start_path, OUTPUT_DIR, 'project.html')
    with open(graph_path, 'w', encoding='utf-8') as f:
        f.write(html)

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
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Headers for output files
    dependencies_header = (
        f"# {DEPENDENCIES}\n"
        "# Description: Contains the project's dependencies.\n"
        "# The first section lists all external libraries imported in the project (excluding local modules).\n"
        "# Following sections list, per file, the imported modules and used functions/classes.\n"
        "# Usage: Open this file to view the project's dependencies."
    )
    tree_files_header = (
        f"# {TREE_FILES}\n"
        "# Description: Represents the directory and file structure of the project.\n"
        "# For Python files, the module-level docstring (if available) is appended as a comment.\n"
        "# Items matching IGNORE are marked as 'ignored'.\n"
        "# Usage: Open this file to review the project's file hierarchy."
    )
    map_definitions_header = (
        f"# {MAP_DEFINITIONS}\n"
        "# Description: Contains detailed definitions of all entities (functions, classes, and nested definitions) in each Python file.\n"
        "# Items matching IGNORE are marked as 'ignored' and are not processed for definitions.\n"
        "# Note: 'Args' and 'Returns' sections are nested under the corresponding function.\n"
        "# Usage: Open this file to inspect the project's internal definitions."
    )
    stat_header = (
        f"# {STATS}\n"
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
    write_file(DEPENDENCIES, dependencies_header, dependencies_lines)
    write_file(TREE_FILES, tree_files_header, tree_files_lines)
    write_file(MAP_DEFINITIONS, map_definitions_header, map_definitions_lines)
    write_file(STATS, stat_header, stat_lines)

    # Print completion message with statistics to terminal.
    print("Indexing complete.")
    print(f"Number of directories: {dirs_count}")
    print(f"Number of files: {files_count}")
    print(f"Total number of lines: {lines_count}")

    write_graph_html(start_dir)
    print(f"Generated dependency graph: {os.path.join(OUTPUT_DIR, 'project.html')}")
