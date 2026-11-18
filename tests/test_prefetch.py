"""Verify one-part lookahead, error propagation, and bounded shutdown."""

import threading
import tempfile
from pathlib import Path
import unittest

from src.infer.prefetch import prefetch_parts
from src.infer.direct import iter_dataset_parts


class PrefetchTests(unittest.TestCase):
    def test_reader_overlaps_consumer_and_stops_at_limit(self):
        started = threading.Event()
        release = threading.Event()
        read = []

        def source():
            try:
                read.append(0)
                yield {"part": 0}, 0
                started.set()
                release.wait(3)
                read.append(1)
                yield {"part": 1}, 1
                read.append(2)
                yield {"part": 2}, 2
            finally:
                read.append("closed")

        parts = prefetch_parts(source(), limit=2)
        self.assertEqual(next(parts)[1], 0)
        self.assertTrue(started.wait(2), "next read did not overlap consumer")
        release.set()
        self.assertEqual(next(parts)[1], 1)
        with self.assertRaises(StopIteration):
            next(parts)
        self.assertEqual(read, [0, 1, "closed"])

    def test_prefetch_crosses_episode_boundary(self):
        started = threading.Event()
        release = threading.Event()
        with tempfile.TemporaryDirectory() as temporary:
            paths = [Path(temporary) / str(i) for i in range(2)]
            for path in paths:
                path.write_bytes(b"data")
            episodes = [
                ({"episode_index": i, "length": 2}, path, 30, "camera")
                for i, path in enumerate(paths)
            ]

            def reader(root, index, path, length, image_key):
                if index == 1:
                    started.set()
                    release.wait(3)
                yield {"part": 0}, {"main": index}

            parts = prefetch_parts(
                iter_dataset_parts(Path(temporary), episodes, reader), limit=2
            )
            self.assertEqual(next(parts)[2]["episode_index"], 0)
            self.assertTrue(
                started.wait(2), "next episode was not prepared concurrently"
            )
            release.set()
            self.assertEqual(next(parts)[2]["episode_index"], 1)
            parts.close()

    def test_reader_exception_propagates_and_closes(self):
        closed = []

        def source():
            try:
                yield {"part": 1}, 1
                raise ValueError("broken input")
            finally:
                closed.append(True)

        parts = prefetch_parts(source())
        self.assertEqual(next(parts)[1], 1)
        with self.assertRaisesRegex(ValueError, "broken input"):
            next(parts)
        self.assertEqual(closed, [True])

    def test_close_stops_reader(self):
        closed = []

        def source():
            try:
                while True:
                    yield {"part": 0}, object()
            finally:
                closed.append(True)

        parts = prefetch_parts(source())
        next(parts)
        parts.close()
        self.assertEqual(closed, [True])
