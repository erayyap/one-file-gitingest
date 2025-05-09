#!/usr/bin/env python3

import os
import re
import argparse
import sys
import fnmatch

# Common binary file extensions to skip by default if no specific include/exclude is given
# for them. This is a heuristic.
DEFAULT_BINARY_EXTENSIONS = {
    '.exe', '.dll', '.so', '.a', '.o', '.obj',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp',
    '.mp3', '.wav', '.ogg', '.flac',
    '.mp4', '.avi', '.mov', '.mkv', '.webm',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.tar', '.gz', '.bz2', '.rar', '.7z',
    '.iso', '.img', '.bin', '.dat',
    '.pyc', '.pyo',
    '.class', '.jar',
    '.sqlite', '.db',
    '.eot', '.otf', '.ttf', '.woff', '.woff2'
}

# Directories to generally ignore
DEFAULT_IGNORE_DIRS = {
    '.git', '.hg', '.svn',
    '__pycache__', '.pytest_cache', '.mypy_cache',
    'node_modules', 'bower_components',
    '.vscode', '.idea', '.project', '.settings',
    'build', 'dist', 'target', 'out',
    'venv', '.venv', 'env', '.env'
}

MAX_FILE_SIZE_DEFAULT_MB = 5
BYTES_IN_MB = 1024 * 1024

def is_likely_binary_file(filepath, file_content_sample):
    """
    Heuristic to check if a file is likely binary.
    Checks extension and a sample of content for null bytes.
    """
    _, ext = os.path.splitext(filepath)
    if ext.lower() in DEFAULT_BINARY_EXTENSIONS:
        return True
    try:
        if file_content_sample.count(b'\x00') > len(file_content_sample) * 0.1: # If >10% null bytes
            return True
    except AttributeError:
        pass
    return False

def should_process_file(
    filepath_relative_to_repo, # This is the path used for matching patterns
    include_regexes,
    exclude_regexes,
    ignore_dirs_set, # This set is for individual component checks if needed (mostly handled by os.walk now)
    is_binary_check=True,
    file_content_sample=None, # Sample read from the full path
    verbose=False
):
    """
    Determines if a file should be processed based on include/exclude patterns
    and other checks.
    `filepath_relative_to_repo` is used for regex matching.
    `file_content_sample` is used for binary detection if provided.
    """
    # 1. Check against ignore_dirs for path components (redundant if os.walk is filtering dirs)
    path_parts = set(filepath_relative_to_repo.split(os.sep))
    if any(part in ignore_dirs_set for part in path_parts):
        if verbose:
            print(f"Skipping (ignored directory component in path): {filepath_relative_to_repo}", file=sys.stderr)
        return False

    # 2. Apply exclude regexes first
    if exclude_regexes:
        for pattern in exclude_regexes:
            if pattern.search(filepath_relative_to_repo):
                if verbose:
                    print(f"Skipping (excluded by pattern matching '{pattern.pattern}'): {filepath_relative_to_repo}", file=sys.stderr)
                return False

    # 3. Apply include regexes if provided
    if include_regexes:
        included_by_regex = False
        for pattern in include_regexes:
            if pattern.search(filepath_relative_to_repo):
                included_by_regex = True
                break
        if not included_by_regex:
            if verbose:
                print(f"Skipping (not included by any pattern): {filepath_relative_to_repo}", file=sys.stderr)
            return False

    # 4. Heuristic for binary files (only if no specific include made it pass)
    if is_binary_check:
        # If the file was explicitly included by a regex, we might want to bypass binary check
        # However, for general safety, let's keep the binary check unless include_regexes is empty
        # (meaning user wants "everything not excluded").
        # A more nuanced approach: if an include_regex specifically targets binary-like extensions, allow it.
        # For now, keep it simple: perform binary check if enabled and sample is available.

        if file_content_sample and is_likely_binary_file(filepath_relative_to_repo, file_content_sample):
            # Check if any include pattern explicitly matched this file. If so, the user might want it.
            # This logic can be tricky. If user says `*.exe` and we check binary, it might get skipped.
            # Current logic: if include_regexes exist and none matched, it's already skipped.
            # If one *did* match, `included_by_regex` is true.
            # So, this binary check is more of a fallback if no includes are specified,
            # or for files that pass includes but are still suspect.

            # Let's refine: skip if binary UNLESS it was explicitly included by a pattern.
            is_explicitly_included = False
            if include_regexes:
                for pattern in include_regexes:
                    if pattern.search(filepath_relative_to_repo):
                        is_explicitly_included = True
                        break
            
            if not is_explicitly_included: # If not explicitly included by a user pattern, and it looks binary, skip
                if verbose:
                    print(f"Skipping (likely binary and not explicitly included): {filepath_relative_to_repo}", file=sys.stderr)
                return False
            elif verbose: # It is explicitly included, but looks binary. Inform user.
                 print(f"Warning: Including '{filepath_relative_to_repo}' which appears binary but matched an include pattern.", file=sys.stderr)


    return True

def generate_tree_display(filepaths, repo_name="."):
    """
    Generates a string representation of the directory structure.
    """
    if not filepaths:
        return f"Repository Structure ({repo_name}):\n(No files included)\n---\n"

    tree_lines = [f"Repository Structure ({repo_name}):"]
    
    # Build the structure: nested dictionaries
    # Files will be marked with a None value, directories will be dicts
    root_structure = {}
    for path_str in sorted(list(set(filepaths))): # Unique, sorted paths
        parts = path_str.split(os.sep)
        current_level = root_structure
        for i, part in enumerate(parts):
            if i == len(parts) - 1: # This is the file part
                current_level[part] = None # Mark as a file
            else: # This is a directory part
                current_level = current_level.setdefault(part, {})
                # If part was already a file (None), and now we try to make it a dir ({}),
                # setdefault will correctly make it a dir. This assumes paths are consistent.
                if current_level is None: # Should not happen if input paths are just files
                    print(f"Warning: Path conflict detected for {part} in tree generation.", file=sys.stderr)
                    current_level = {} # Recover by making it a dir
    
    def _build_tree_lines_recursive(node, current_prefix=""):
        lines = []
        # Sort items alphabetically for consistent tree output
        # Directories (dict values) will naturally interleave with files (None values) based on name
        items = sorted(node.items(), key=lambda item: item[0].lower())
        
        for i, (name, child_node) in enumerate(items):
            is_last_entry_in_level = (i == len(items) - 1)
            connector = "└── " if is_last_entry_in_level else "├── "
            lines.append(f"{current_prefix}{connector}{name}")
            
            if isinstance(child_node, dict): # If it's a directory, recurse
                child_prefix_extension = "    " if is_last_entry_in_level else "│   "
                lines.extend(_build_tree_lines_recursive(child_node, current_prefix + child_prefix_extension))
        return lines

    tree_lines.extend(_build_tree_lines_recursive(root_structure))
    return "\n".join(tree_lines) + "\n---\n"


def ingest_repo(
    repo_path,
    include_patterns=None,
    exclude_patterns=None,
    output_file=None,
    max_file_size_mb=MAX_FILE_SIZE_DEFAULT_MB,
    verbose=False,
    no_git_check=False
):
    if not os.path.isdir(repo_path):
        print(f"Error: Repository path '{repo_path}' not found or not a directory.", file=sys.stderr)
        return

    abs_repo_path = os.path.abspath(repo_path)
    repo_base_name = os.path.basename(abs_repo_path)

    if not no_git_check and not os.path.isdir(os.path.join(abs_repo_path, ".git")):
        print(f"Warning: '{repo_base_name}' does not appear to be a Git repository (no .git directory). Proceeding anyway.", file=sys.stderr)

    compiled_include_regexes = []
    if include_patterns:
        for i, p_str in enumerate(include_patterns):
            try:
                translated = fnmatch.translate(p_str)
                if verbose: print(f"DEBUG: Include glob '{p_str}' -> regex '{translated}'", file=sys.stderr)
                compiled_include_regexes.append(re.compile(translated))
            except re.error as e:
                print(f"Error: Invalid regex from include glob '{p_str}': {e}", file=sys.stderr); sys.exit(1)

    compiled_exclude_regexes = []
    if exclude_patterns:
        for i, p_str in enumerate(exclude_patterns):
            try:
                translated = fnmatch.translate(p_str)
                if verbose: print(f"DEBUG: Exclude glob '{p_str}' -> regex '{translated}'", file=sys.stderr)
                compiled_exclude_regexes.append(re.compile(translated))
            except re.error as e:
                print(f"Error: Invalid regex from exclude glob '{p_str}': {e}", file=sys.stderr); sys.exit(1)
    
    current_ignore_dirs = DEFAULT_IGNORE_DIRS.copy()
    all_content_parts = []
    included_relative_paths = [] # For tree generation
    max_file_size_bytes = max_file_size_mb * BYTES_IN_MB

    for root, dirs, files in os.walk(abs_repo_path, topdown=True):
        dirs[:] = [d for d in dirs if d not in current_ignore_dirs]

        for filename in files:
            full_filepath = os.path.join(root, filename)
            relative_filepath = os.path.relpath(full_filepath, abs_repo_path)

            try:
                file_size = os.path.getsize(full_filepath)
                if file_size > max_file_size_bytes:
                    if verbose: print(f"Skipping (file too large: {file_size / BYTES_IN_MB:.2f}MB > {max_file_size_mb}MB): {relative_filepath}", file=sys.stderr)
                    continue
            except OSError as e:
                if verbose: print(f"Skipping (error getting size for {relative_filepath}: {e})", file=sys.stderr)
                continue

            file_content_sample_for_check = None
            try:
                with open(full_filepath, 'rb') as f_sample:
                    file_content_sample_for_check = f_sample.read(1024)
            except IOError:
                if verbose: print(f"Skipping (IOError reading sample for binary check): {relative_filepath}", file=sys.stderr)
                continue

            if should_process_file(
                filepath_relative_to_repo=relative_filepath,
                include_regexes=compiled_include_regexes,
                exclude_regexes=compiled_exclude_regexes,
                ignore_dirs_set=current_ignore_dirs, # Pass for consistency, though os.walk handles most
                is_binary_check=True,
                file_content_sample=file_content_sample_for_check,
                verbose=verbose
            ):
                try:
                    with open(full_filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    all_content_parts.append(f"--- {relative_filepath} ---\n{content}\n")
                    included_relative_paths.append(relative_filepath) # Add for tree
                    if verbose: print(f"Including: {relative_filepath}", file=sys.stderr)
                except Exception as e:
                    if verbose: print(f"Error reading {relative_filepath}: {e}", file=sys.stderr)

    tree_header = generate_tree_display(included_relative_paths, repo_base_name)
    final_output = tree_header + "\n".join(all_content_parts) # Prepend tree

    if output_file:
        try:
            with open(output_file, 'w', encoding='utf-8') as f: f.write(final_output)
            print(f"Output written to {output_file}", file=sys.stderr)
        except IOError as e:
            print(f"Error writing to output file {output_file}: {e}", file=sys.stderr)
    else:
        sys.stdout.write(final_output)

def main():
    parser = argparse.ArgumentParser(
        description="Concatenate files from a repository, with glob/regex filtering, for LLM ingestion.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "repo_path",
        help="Path to the local repository directory."
    )
    parser.add_argument(
        "-i", "--include",
        action="append",
        dest="include_patterns",
        metavar="GLOB_OR_REGEX",
        help="Shell-like glob pattern (e.g., '*.py', 'docs/*') to include files. \n"
             "Paths are relative to repo root. Can be specified multiple times.\n"
             "If any include pattern matches, the file is a candidate.\n"
             "Glob patterns are automatically translated to regexes.\n"
             "Example (glob): '*.py' or 'src/*.js'"
    )
    parser.add_argument(
        "-e", "--exclude",
        action="append",
        dest="exclude_patterns",
        metavar="GLOB_OR_REGEX",
        help="Shell-like glob pattern (e.g., '*.log', 'tests/*') to exclude files. \n"
             "Paths are relative to repo root. Can be specified multiple times.\n"
             "Exclude patterns take precedence. Glob patterns are translated to regexes.\n"
             "Example (glob): '*.tmp' or 'dist/*'"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_file",
        metavar="FILE",
        help="File to write the concatenated output to. Prints to stdout if not specified."
    )
    parser.add_argument(
        "--max-file-size",
        type=float,
        default=MAX_FILE_SIZE_DEFAULT_MB,
        dest="max_file_size_mb",
        metavar="MB",
        help=f"Maximum size for individual files in MB (default: {MAX_FILE_SIZE_DEFAULT_MB}MB)."
    )
    parser.add_argument(
        "--no-git-check",
        action="store_true",
        help="Do not check for a .git directory. Process any specified directory."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output (prints skipped files, reasons, and pattern translations to stderr)."
    )

    args = parser.parse_args()

    ingest_repo(
        repo_path=args.repo_path,
        include_patterns=args.include_patterns,
        exclude_patterns=args.exclude_patterns,
        output_file=args.output_file,
        max_file_size_mb=args.max_file_size_mb,
        verbose=args.verbose,
        no_git_check=args.no_git_check
    )

if __name__ == "__main__":
    main()