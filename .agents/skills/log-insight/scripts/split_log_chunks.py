"""Split a log file into tail chunks for Codex log insight analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse required command line arguments."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Split a log file from the end into fixed-size character chunks.",
    )
    parser.add_argument("--path", required=True, help="Source log file path.")
    parser.add_argument("--context", required=True, type=int, help="Context window in thousands of characters.")
    parser.add_argument("--chunks", required=True, type=int, help="Maximum number of chunks to produce.")
    parser.add_argument("--output-dir", required=True, help="Directory where chunk files will be written.")
    parser.add_argument("--encoding", required=True, help="Text encoding used to read and write log chunks.")
    return parser.parse_args()


def build_chunks(text: str, requested_chunks: int, chunk_size_chars: int) -> list[tuple[int, int, str]]:
    """Return oldest-to-newest chunk ranges and text."""
    chunks: list[tuple[int, int, str]] = []
    end: int = len(text)

    for _ in range(requested_chunks):
        if end <= 0:
            break
        start: int = max(0, end - chunk_size_chars)
        chunks.append((start, end, text[start:end]))
        end = start

    chunks.reverse()
    return chunks


def write_chunks(
    chunks: list[tuple[int, int, str]],
    output_dir: Path,
    encoding: str,
) -> list[dict[str, Any]]:
    """Write chunk files and return manifest entries."""
    output_dir.mkdir(parents=True, exist_ok=False)
    total_chunks: int = len(chunks)
    manifest_chunks: list[dict[str, Any]] = []

    for index, (start, end, chunk_text) in enumerate(chunks, start=1):
        chunk_path: Path = output_dir / f"chunk_{index:03d}_of_{total_chunks:03d}.log"
        chunk_path.write_text(chunk_text, encoding=encoding)
        manifest_chunks.append(
            {
                "number": index,
                "total": total_chunks,
                "path": str(chunk_path.resolve()),
                "char_start": start,
                "char_end": end,
                "chars": len(chunk_text),
            },
        )

    return manifest_chunks


def main() -> None:
    """Split the requested log file and print a JSON manifest."""
    args: argparse.Namespace = parse_args()
    source_path: Path = Path(args.path).resolve()
    output_dir: Path = Path(args.output_dir).resolve()

    if args.context <= 0:
        raise ValueError("--context must be greater than zero")
    if args.chunks <= 0:
        raise ValueError("--chunks must be greater than zero")
    if not source_path.is_file():
        raise FileNotFoundError(f"Log file not found: {source_path}")

    context_chars: int = args.context * 1000
    chunk_size_chars: int = int(context_chars * 0.70)
    if chunk_size_chars <= 0:
        raise ValueError("Calculated chunk size must be greater than zero")

    text: str = source_path.read_text(encoding=args.encoding, errors="replace")
    chunks: list[tuple[int, int, str]] = build_chunks(
        text=text,
        requested_chunks=args.chunks,
        chunk_size_chars=chunk_size_chars,
    )
    manifest_chunks: list[dict[str, Any]] = write_chunks(
        chunks=chunks,
        output_dir=output_dir,
        encoding=args.encoding,
    )

    manifest: dict[str, Any] = {
        "source_path": str(source_path),
        "context": args.context,
        "context_chars": context_chars,
        "chunk_size_chars": chunk_size_chars,
        "requested_chunks": args.chunks,
        "actual_chunks": len(manifest_chunks),
        "total_chars": len(text),
        "analyzed_chars": sum(chunk["chars"] for chunk in manifest_chunks),
        "chunks": manifest_chunks,
    }
    print(json.dumps(manifest, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
