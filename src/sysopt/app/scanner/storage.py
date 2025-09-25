import os
from typing import List, Tuple

def find_largest_files(start_path: str = None, max_files: int = 25) -> List[Tuple[int, str]]:
    """
    Scans the given directory (or home directory by default) and returns the largest files.

    This function recursively walks through all subdirectories starting from 'start_path',
    collects file paths and their sizes, and returns the top 'max_files' largest files
    sorted by size in descending order.

    Args:
        start_path (str, optional): The root directory to start scanning from.
                                    If None, defaults to the user's home directory.
        max_files (int, optional): The maximum number of largest files to return.
                                   Defaults to 25.

    Returns:
        List[Tuple[int, str]]: A list of tuples where each tuple contains:
            - int: File size in bytes
            - str: Full path to the file

    Example:
        >>> find_largest_files("/home/user", max_files=5)
        [(1073741824, '/home/user/big_file.dat'), (536870912, '/home/user/another_file.zip'), ...]
    """
    if start_path is None:
        start_path = os.path.expanduser("~")

    files = []

    # Walk through all directories and subdirectories
    for root, _, filenames in os.walk(start_path):
        for filename in filenames:
            full_path = os.path.join(root, filename)

            # Attempt to get file size
            try:
                size = os.path.getsize(full_path)
                files.append((size, full_path))
            except OSError:
                # Skip files that cannot be accessed (e.g., permission denied)
                continue

    sorted_files = sorted(files, key=lambda x: x[0], reverse=True)
    return sorted_files[:max_files]

def format_bytes(size_in_bytes: int) -> str:
    """
    Converts a size in bytes to a human-readable string (e.g., KB, MB, GB).

    Args:
        size_in_bytes (int): Size in bytes.

    Returns:
        str: Human-readable size string (e.g., "2.5 GB", "1024.0 MB").
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} PB"

def print_largest_files(start_path: str = None, max_files: int = 25):
    """
    Prints the largest files found in the given directory in a human-readable format.

    Args:
        start_path (str, optional): Directory to scan. Defaults to home directory.
        max_files (int, optional): Number of largest files to display. Defaults to 25.
    """
    files = find_largest_files(start_path, max_files)
    print(f"Top {len(files)} largest files:")
    for size, path in files:
        print(f"{format_bytes(size):>10} | {path}")

if __name__ == "__main__":
    print_largest_files(max_files=10)