import os
import shutil


def remove_cache_dirs(root_dir):
    dirs_to_remove = [
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        ".coverage",
        ".tox",
        ".eggs",
        "build",
        "dist",
    ]

    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        for dirname in dirnames:
            # Check if the directory matches any of the cache directories
            if dirname in dirs_to_remove:
                dir_to_remove = os.path.join(dirpath, dirname)
                print(f"Deleting: {dir_to_remove}")
                shutil.rmtree(dir_to_remove)


if __name__ == "__main__":
    project_dir = os.getcwd()  # Get the current working directory
    remove_cache_dirs(project_dir)
