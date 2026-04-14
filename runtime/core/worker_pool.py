from __future__ import annotations

import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_STOP = threading.Event()


def _handle_stop(signum, _frame) -> None:
    print(f"[worker-pool] stop signal received ({signum})", flush=True)
    _STOP.set()


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    print("[worker-pool] starting", flush=True)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="ai-worker") as _executor:
        print("[worker-pool] started", flush=True)
        while not _STOP.is_set():
            time.sleep(1.0)

    print("[worker-pool] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
