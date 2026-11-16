"""Map temporal segments to native frames and optional boundary flags."""

from bisect import bisect_left, bisect_right
from fractions import Fraction


def frame_span(video, start_s, end_s):
    start = Fraction(str(start_s)) * 1_000_000
    end = Fraction(str(end_s)) * 1_000_000
    pts = video.pts_us
    first = min(max(0, bisect_right(pts, start) - 1), len(pts) - 1)
    last = max(first + 1, min(bisect_left(pts, end), len(pts)))
    return first, last


def boundary_flags(segments, frame_count, merge_gap=30):
    if merge_gap < 0:
        raise ValueError("flag-merge-gap must be nonnegative")
    endpoints = sorted(
        {
            row[key]
            for row in segments
            for key in ("start_frame", "end_frame")
            if 10 <= row[key] < frame_count - 10
        }
    )
    groups = []
    for endpoint in endpoints:
        if groups and endpoint - groups[-1][-1] < merge_gap:
            groups[-1].append(endpoint)
        else:
            groups.append([endpoint])
    return [(2 * sum(group) + len(group)) // (2 * len(group)) for group in groups]
