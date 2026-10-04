import os
from pathlib import Path


def pick_oriented_file(psd_path, vertical, horizontal, square):
    """Return the file matching the template's orientation (by PSD filename), or None.

    Used by both artwork and video modes. None means: the filename has no orientation
    keyword, OR that orientation's file was not provided (empty string) — in both cases
    the caller skips the template. Precedence: square > horizontal > vertical.
    """
    name = Path(psd_path).stem.lower()
    if "square" in name:
        return square or None
    if "horizontal" in name:
        return horizontal or None
    if "vertical" in name:
        return vertical or None
    return None


def find_templates(root_folder: str, product_names: list[str]) -> dict[str, list[Path]]:
    """
    Walk the templates directory tree and match product names to PSD files.

    Matching is case-insensitive substring: product name "Mug" matches any
    PSD whose relative path contains "mug" (e.g., "Coffee-Mug-Mockup.psd"
    or "Mugs/template.psd").

    Returns a dict mapping each product name to its list of matched PSD paths.
    Products with no matches map to an empty list.
    """
    # Collect all PSD files with their paths relative to root
    psd_files: list[tuple[Path, str]] = []
    root = Path(root_folder)

    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.lower().endswith(".psd"):
                full_path = Path(dirpath) / filename
                relative = str(full_path.relative_to(root))
                psd_files.append((full_path, relative.lower()))

    # Match each product name against the collected PSD paths
    results: dict[str, list[Path]] = {}

    for name in product_names:
        name_stripped = name.strip()
        if not name_stripped:
            continue
        keyword = name_stripped.lower()
        matches = [path for path, rel in psd_files if keyword in rel]
        results[name_stripped] = sorted(matches, key=lambda p: p.name.lower())

    return results
