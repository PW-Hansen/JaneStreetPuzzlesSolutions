"""Read the cell contents currently displayed, without committing previews."""
from .pentominoes import preview_record


def displayed_entries(data):
    preview = preview_record(data)
    entries = {}
    if preview is not None:
        entries.update(preview['entries'])
        entries.update(preview.get('forced_entries', {}))
    entries.update(data['entries'])
    return entries
