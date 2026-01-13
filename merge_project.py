import os
import sys

def merge_project():
    """
    Project Merger Script
    Consolidates text-based code files into a single _FULL_CODEBASE.txt file.
    Includes a project tree structure at the beginning.
    """
    # 1. Configuration
    target_dir = os.path.dirname(os.path.abspath(__file__))
    output_filename = "_FULL_CODEBASE.txt"
    output_path = os.path.join(target_dir, output_filename)
    
    ignore_dirs = {'.git', '__pycache__', 'venv', 'env', 'node_modules', '.vscode', '.idea', 'dist', 'build'}
    ignore_files = {'.env', output_filename, 'merge_project.py'} # Added self and output to ignore
    
    # Extensions to include
    include_extensions = {
        '.py', '.js', '.ts', '.tsx', '.html', '.css', 
        '.json', '.md', '.sql', '.txt', '.xml', '.yaml'
    }
    
    # Extensions to explicitly ignore (binary)
    ignore_extensions = {'.png', '.jpg', '.pyc', '.exe', '.dll', '.so', '.dylib'}

    print(f"[*] Starting merge in: {target_dir}")
    print(f"[*] Output file: {output_path}")

    # 2. Collect files and build tree structure
    files_to_merge = []
    tree_lines = []

    def build_tree(current_path, indent=""):
        items = sorted(os.listdir(current_path))
        for i, item in enumerate(items):
            item_path = os.path.join(current_path, item)
            rel_path = os.path.relpath(item_path, target_dir)
            
            # Skip ignored directories
            if os.path.isdir(item_path):
                if item in ignore_dirs:
                    continue
            
            # Skip ignored files or non-text based files
            if os.path.isfile(item_path):
                ext = os.path.splitext(item)[1].lower()
                if item in ignore_files or ext not in include_extensions:
                    continue
                files_to_merge.append(rel_path)

            # Add to tree
            connector = "├── " if i < len(items) - 1 else "└── "
            if os.path.isdir(item_path):
                tree_lines.append(f"{indent}{connector}{item}/")
                new_indent = indent + ("│   " if i < len(items) - 1 else "    ")
                build_tree(item_path, new_indent)
            else:
                # Re-check if it's a file we want to show in the tree
                ext = os.path.splitext(item)[1].lower()
                if item not in ignore_files and ext in include_extensions:
                    tree_lines.append(f"{indent}{connector}{item}")

    # Start tree building from target_dir
    tree_lines.append(f"{os.path.basename(target_dir)}/")
    build_tree(target_dir)

    # 3. Write to output file
    try:
        with open(output_path, 'w', encoding='utf-8') as outfile:
            # Write Tree Structure
            outfile.write("================ PROJECT TREE STRUCTURE ================\n")
            outfile.write("\n".join(tree_lines))
            outfile.write("\n\n")

            # Write individual file contents
            for rel_path in files_to_merge:
                abs_path = os.path.join(target_dir, rel_path)
                outfile.write(f"\n================ FILE: {rel_path} ================\n")
                
                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='replace') as infile:
                        content = infile.read()
                        # Mask potential API keys (simple heuristic)
                        # The user asked to skip .env, which we already do.
                        # We could add more masking here if needed.
                        outfile.write(content)
                except Exception as e:
                    outfile.write(f"Error reading file: {str(e)}\n")
                
                outfile.write("\n")

        print(f"[+] Successfully created {output_filename}")
        print(f"[+] Total files merged: {len(files_to_merge)}")

    except Exception as e:
        print(f"[-] Error writing output file: {e}")

if __name__ == "__main__":
    merge_project()
