"""
Parse GitHub unified diffs into structured per-file chunks for the review pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Matches unified-diff hunk headers, e.g. @@ -10,5 +10,6 @@ optional context
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass
class DiffChunk:
    """
    One file's worth of diff data, ready for an LLM or static analyzer.

    Attributes:
        filename: Path of the file in the repo (from the +++ line).
        patch: Raw patch body (hunk headers and +/- / context lines).
        additions: Number of lines added (``+``, excluding ``+++``).
        deletions: Number of lines removed (``-``, excluding ``---``).
        context_lines: Unchanged lines from the hunk (leading space).
        changed_lines: 1-based line numbers in the *new* file for added lines.
    """

    filename: str
    patch: str
    additions: int
    deletions: int
    context_lines: list[str] = field(default_factory=list)
    changed_lines: list[int] = field(default_factory=list)


def parse_diff(raw_diff: str) -> list[DiffChunk]:
    """
    Split a raw GitHub unified diff into :class:`DiffChunk` objects (one per file).

    Skips binary files and sections without patch hunks. Counts and line numbers
    are derived by walking each hunk after its ``@@`` header.
    """
    if not raw_diff or not raw_diff.strip():
        return []

    chunks: list[DiffChunk] = []

    # GitHub concatenates per-file diffs; each section begins with "diff --git"
    sections = raw_diff.split("diff --git")

    for section in sections:
        if not section.strip():
            continue

        # Reattach the delimiter stripped by split()
        file_section = "diff --git" + section

        # Binary assets have no line-level patch to review
        if "Binary files" in file_section:
            continue

        filename = _extract_filename(file_section)
        if not filename:
            continue

        patch_lines = _extract_patch_lines(file_section)
        if not patch_lines:
            continue

        patch = "\n".join(patch_lines)
        additions, deletions, context_lines, changed_lines = _analyze_patch_lines(
            patch_lines
        )

        chunks.append(
            DiffChunk(
                filename=filename,
                patch=patch,
                additions=additions,
                deletions=deletions,
                context_lines=context_lines,
                changed_lines=changed_lines,
            )
        )

    return chunks


def chunk_large_diff(
    chunks: list[DiffChunk], max_lines: int = 300
) -> list[DiffChunk]:
    """
    Split any chunk whose patch exceeds ``max_lines`` into smaller pieces.

    Oversized chunks are replaced by multiple chunks with the same stats
    recalculated per slice. Filenames gain a `` (part N)`` suffix.
    """
    result: list[DiffChunk] = []

    for chunk in chunks:
        patch_line_list = chunk.patch.splitlines() if chunk.patch else []

        if len(patch_line_list) <= max_lines:
            result.append(chunk)
            continue

        # Slice the patch into windows of at most max_lines
        part_index = 1
        for start in range(0, len(patch_line_list), max_lines):
            slice_lines = patch_line_list[start : start + max_lines]
            part_patch = "\n".join(slice_lines)
            additions, deletions, context_lines, changed_lines = _analyze_patch_lines(
                slice_lines
            )

            result.append(
                DiffChunk(
                    filename=f"{chunk.filename} (part {part_index})",
                    patch=part_patch,
                    additions=additions,
                    deletions=deletions,
                    context_lines=context_lines,
                    changed_lines=changed_lines,
                )
            )
            part_index += 1

    return result


def _extract_filename(file_section: str) -> str | None:
    """Read the post-image path from a ``+++ b/path`` line."""
    for line in file_section.splitlines():
        if line.startswith("+++"):
            # +++ b/src/foo.py  or  +++ /dev/null
            path = line[4:].strip()
            if path.startswith("b/"):
                return path[2:]
            return path
    return None


def _extract_patch_lines(file_section: str) -> list[str]:
    """
    Collect hunk content: ``@@`` headers plus context/add/delete lines.

    Stops including metadata lines (diff --git, index, ---, +++).
    """
    patch_lines: list[str] = []
    in_hunk = False

    for line in file_section.splitlines():
        if line.startswith("@@"):
            in_hunk = True
            patch_lines.append(line)
            continue

        if not in_hunk:
            continue

        # Lines inside a hunk: context, additions, deletions, or "\ No newline..."
        if line.startswith((" ", "+", "-", "\\")):
            patch_lines.append(line)

    return patch_lines


def _analyze_patch_lines(
    patch_lines: list[str],
) -> tuple[int, int, list[str], list[int]]:
    """
    Walk patch lines and compute counts, context, and new-file line numbers.

    Returns:
        (additions, deletions, context_lines, changed_lines)
    """
    additions = 0
    deletions = 0
    context_lines: list[str] = []
    changed_lines: list[int] = []

    new_line: int | None = None

    for line in patch_lines:
        header_match = _HUNK_HEADER_RE.match(line)
        if header_match:
            # Start counting from the new-file side of the hunk
            new_line = int(header_match.group(2))
            continue

        if new_line is None:
            continue

        if line.startswith("+++") or line.startswith("---"):
            continue

        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
            changed_lines.append(new_line)
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            # Removed lines exist only on the old side; new_line does not advance
        elif line.startswith(" "):
            context_lines.append(line)
            new_line += 1
        # "\\ No newline at end of file" and other markers are ignored

    return additions, deletions, context_lines, changed_lines


if __name__ == "__main__":
    # Quick manual check: parse a tiny two-file diff and print structure
    SAMPLE_DIFF = """diff --git a/src/utils.py b/src/utils.py
index 1111111..2222222 100644
--- a/src/utils.py
+++ b/src/utils.py
@@ -1,4 +1,5 @@
 def greet(name):
-    return "hi"
+    return f"hello, {name}"
+
 def add(a, b):
     return a + b
diff --git a/README.md b/README.md
index 3333333..4444444 100644
--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@
 # Project
+Added docs line
"""

    parsed = parse_diff(SAMPLE_DIFF)
    print(f"Parsed {len(parsed)} file chunk(s):\n")
    for chunk in parsed:
        print(f"  {chunk.filename}")
        print(f"    additions={chunk.additions}, deletions={chunk.deletions}")
        print(f"    changed_lines={chunk.changed_lines}")
        print(f"    context_lines={len(chunk.context_lines)}")
        print(f"    patch ({len(chunk.patch.splitlines())} lines):")
        for patch_line in chunk.patch.splitlines():
            print(f"      {patch_line}")
        print()

    # Demonstrate splitting an oversized chunk
    big = DiffChunk(
        filename="big.py",
        patch="\n".join(f"+line {i}" for i in range(350)),
        additions=350,
        deletions=0,
    )
    split = chunk_large_diff([big], max_lines=300)
    print(f"chunk_large_diff: 1 chunk -> {len(split)} part(s)")
    for part in split:
        print(f"  {part.filename}: {len(part.patch.splitlines())} patch lines")
