"""One-part lookahead without concurrent GPU work or unbounded buffering."""

from concurrent.futures import ThreadPoolExecutor
import json
import time


def prefetch_parts(source, limit=0):
    iterator = iter(source)
    end = object()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="flora-reader")
    pending = None

    def read_next():
        started = time.monotonic()
        item = next(iterator, end)
        if item is not end:
            print(
                "FLORA_RUNTIME "
                + json.dumps(
                    {
                        "event": "part_prefetched",
                        "part": item[0].get("part", item[0].get("id")),
                        "episode": item[0].get(
                            "episode_index",
                            item[2].get("episode_index")
                            if len(item) > 2 and isinstance(item[2], dict)
                            else None,
                        ),
                        "elapsed_s": round(time.monotonic() - started, 3),
                    }
                ),
                flush=True,
            )
        return item

    try:
        pending = executor.submit(read_next)
        count = 0
        while True:
            item = pending.result()
            pending = None
            if item is end:
                break
            count += 1
            if not limit or count < limit:
                pending = executor.submit(read_next)
            yield item
            # Do not keep a reference to the previous chunk while reading another.
            item = None
            if pending is None:
                break
    finally:
        if pending is not None:
            pending.cancel()
        executor.shutdown(wait=True, cancel_futures=True)
        close = getattr(iterator, "close", None)
        if close is not None:
            close()
