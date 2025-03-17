# Indexer-Py

Indexer-Py is a minimalistic Python project indexing tool built entirely with Python's standard libraries. It is designed to help you quickly restore context for your project by generating several output files that describe the project’s structure, detailed definitions, and dependencies. This tool is especially useful when used in conjunction with AI agents (e.g., Cursor AI) to provide rapid context recovery from your project's source code.

## Features

- **File Tree (`tree_files.txt`):**  
  Generates a tree view of your project's directory and file structure. For Python files, the module-level docstring is appended as a comment. Items listed in the ignore list are marked as "ignored" and are not further processed.

- **Detailed Definitions (`map_definitions.txt`):**  
  Provides a detailed tree of all internal definitions in your Python files. It includes classes, functions (including async functions), and nested definitions. 'Args' and 'Returns' sections extracted from docstrings are nested under the corresponding functions.

- **Dependency Listing (`dependencies.txt`):**  
  Lists external libraries (top-level names) imported in your project and, for each file, shows its imported modules and used functions/classes.

- **Project Statistics (`stat.txt`):**  
  Summarizes the project by counting directories, files (excluding ignored items), total lines, and total bytes.

## Usage

1. **Prepare your project:**  
   Place `indexer.py` (the script) in the root of your Python project.

2. **Customize the Ignore List:**  
   The ignore list is a single set called `IGNORE` located at the top of the script. It supports shell-style wildcards (masks) and distinguishes directories by a trailing slash.  
   **Default Ignore List:**
   ```
   IGNORE = {
       "__pycache__",
       "indexer_data/",
       "venv/",
       "env/",
       "logs/",
       ".env",
       "indexer.py",
       "bot.log"
   }
   ```
   - To ignore a directory, add its name with a trailing slash (e.g., `"venv/"`).
   - To ignore a file, simply add its name or pattern (e.g., `"bot.log"`).

3. **Run the Script:**  
   Execute the script using Python:
   ```
   python indexer.py
   ```
   The script will create an `indexer_data` directory containing:
   - `dependencies.txt`
   - `tree_files.txt`
   - `map_definitions.txt`
   - `stat.txt`

4. **Terminal Output:**  
   After execution, the script will print a completion message with statistics about the project (number of directories, files, and total lines).

## Integration with AI Agents

Indexer-Py is designed to work seamlessly with AI agents for rapid project context recovery. After running the script, you can provide the generated output files to an AI agent (for example, Cursor AI) to help it understand the structure and dependencies of your project.

### Example Prompt

Below is an example prompt you could send to your AI agent:

> **Prompt:**  
> "I have generated several output files from my project using Indexer-Py. Please analyze the following files to restore the context of my project:
> - `tree_files.txt` – shows the overall file and directory structure.
> - `map_definitions.txt` – provides detailed internal definitions, including functions, classes, and their docstrings.
> - `dependencies.txt` – lists all external libraries and module dependencies.
> - `stat.txt` – summarizes key statistics (number of directories, files, and lines).
>
> Use this information to understand the project's architecture and dependencies."

## Example Outputs

### `tree_files.txt`

```
├── main.py  # This is the main entry point for the application.
├── config.py  # Contains configuration settings.
├── utils/
│   ├── file_manager.py  # Module for managing file operations.
│   └── helpers.py  # Helper functions.
└── models/
    ├── __init__.py
    └── user.py  # Defines the User class and related functions.
```

### `map_definitions.txt`

```
├── main.py  # Main module entry.
│   ├── [Function] start_app  # Initializes the application.
│   │   ├── [Args]
│   │   │   └── config: Application configuration
│   │   ├── [Function] initialize  # Sets up initial state.
│   └── [Function] shutdown  # Cleans up before exit.
```

### `dependencies.txt`

```
Project External Libraries:
  - requests
  - numpy

File: main.py
  Imported Modules:
    - config
    - utils.file_manager
  Used Functions/Classes:
    - start_app
    - shutdown

...
```

### `stat.txt`

```
Number of directories: 5
Number of files: 12
Total number of lines: 3500
Total number of bytes: 120000
```

## Minimalistic and Standard Library Only

Indexer-Py is built entirely on Python’s standard libraries. There is no need to install any external dependencies, making it highly portable and easy to integrate into any Python project.

---

Happy indexing!
