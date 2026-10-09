"""Cooperative cancellation shared by region operations."""

import threading


_region_work = threading.local()


class RegionOperationAborted(Exception):
    def __init__(self):
        super().__init__("Operation aborted. Previous overlays retained.")


def check_region_abort():
    cancel = getattr(_region_work,'cancel',None)
    if cancel is not None and cancel.is_set():
        raise RegionOperationAborted()
