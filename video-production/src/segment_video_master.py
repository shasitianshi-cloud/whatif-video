"""Deterministic lossless segmentation for a frozen Video Master."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PRIMARY_BOUNDARIES = frozenset("。！？")
SECONDARY_BOUNDARIES = frozenset("；，：")


@dataclass(frozen=True)
class Segment:
    segment_id: str
    order: int
    source_start: int
    source_end: int
    text: str
    utf8_byte_length: int

    def to_dict(self) -> dict:
        return asdict(self)


def read_canonical_text(path: Path) -> str:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _boundary_spans(text: str, boundaries: Iterable[str]) -> list[tuple[int, int]]:
    boundary_set = frozenset(boundaries)
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    while index < len(text):
        if text[index] in boundary_set:
            end = index + 1
            while end < len(text) and text[end].isspace():
                end += 1
            spans.append((start, end))
            start = end
            index = end
            continue
        index += 1
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def segment_text(text: str, max_text_characters: int = 3000) -> list[Segment]:
    if max_text_characters < 1:
        raise ValueError("max_text_characters must be positive")
    primary = _boundary_spans(text, PRIMARY_BOUNDARIES)
    final_spans: list[tuple[int, int]] = []
    for start, end in primary:
        if end - start <= max_text_characters:
            final_spans.append((start, end))
            continue
        local = text[start:end]
        secondary = _boundary_spans(local, SECONDARY_BOUNDARIES)
        cursor = start
        for local_start, local_end in secondary:
            piece_start, piece_end = start + local_start, start + local_end
            if piece_end - piece_start > max_text_characters:
                raise ValueError(
                    "source sentence exceeds provider limit and cannot be split "
                    "losslessly at an allowed natural punctuation boundary"
                )
            final_spans.append((piece_start, piece_end))
            cursor = piece_end
        if cursor != end:
            raise AssertionError("secondary segmentation did not cover source span")

    return [
        Segment(
            segment_id=f"seg-{order:03d}",
            order=order,
            source_start=start,
            source_end=end,
            text=text[start:end],
            utf8_byte_length=len(text[start:end].encode("utf-8")),
        )
        for order, (start, end) in enumerate(final_spans, 1)
    ]


def verify_lossless(text: str, segments: list[Segment]) -> dict[str, bool]:
    reconstructed = "".join(segment.text for segment in segments)
    spans_ordered = all(
        segment.source_start == (0 if i == 0 else segments[i - 1].source_end)
        and segment.source_end >= segment.source_start
        and text[segment.source_start : segment.source_end] == segment.text
        for i, segment in enumerate(segments)
    )
    match = reconstructed == text and spans_ordered
    return {
        "segment_reconstruction_match": match,
        "text_loss": len(reconstructed) < len(text) or not match,
        "text_addition": len(reconstructed) > len(text) or not match,
        "text_reorder": not spans_ordered,
    }

