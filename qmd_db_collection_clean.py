"""
remove_all_collections.py — wipe every registered QMD collection so you
can start ingest clean. Run this manually, once, before re-registering
the wiki (and optionally qmd_file) collection.

Usage:
    python remove_all_collections.py
"""

from qmd.qmd_ingest import list_collections, remove_collection

# QMD's `collection list` output looks like:
#   Collections (2):
#   qmd_file (qmd://qmd_file/)
#     Pattern:  **/*.md
#     Files:    8
#     Updated:  8d ago
#   wiki (qmd://wiki/)
#     ...
# Collection names are the lines with no leading whitespace that aren't
# the "Collections (N):" header line.

def get_collection_names() -> list[str]:
    raw = list_collections()
    names = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("Collections ("):
            continue
        if line[0].isspace():
            continue  # indented detail lines (Pattern/Files/Updated)
        # top-level line looks like: "wiki (qmd://wiki/)"
        name = line.split(" ", 1)[0].strip()
        if name:
            names.append(name)
    return names


def main():
    names = get_collection_names()
    if not names:
        print("No collections found.")
        return

    print(f"Found {len(names)} collection(s): {', '.join(names)}")
    for name in names:
        print(f"Removing '{name}'...")
        print(remove_collection(name))

    print("Done. Verify with: qmd collection list")


if __name__ == "__main__":
    main()