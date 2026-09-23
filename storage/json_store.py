"""
Lightweight JSON storage.

Provides a simple interface for reading and writing JSON data files.
Designed to be replaced later by a proper database without changing
the agent logic — consumers use the same read/write/query interface.
"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class JSONStore:
    """
    Simple JSON file-based data store.

    Each 'collection' is a JSON file in the data directory.
    Data is stored as a list of records (dicts).
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info("JSON store initialized at: %s", self.data_dir)

    def _file_path(self, collection: str) -> Path:
        """Get the file path for a collection."""
        return self.data_dir / f"{collection}.json"

    def read_all(self, collection: str) -> list[dict[str, Any]]:
        """Read all records from a collection."""
        filepath = self._file_path(collection)
        if not filepath.exists():
            return []

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else [data]
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Error reading %s: %s", filepath, e)
            return []

    def write_all(self, collection: str, records: list[dict[str, Any]]):
        """Write all records to a collection (overwrites)."""
        filepath = self._file_path(collection)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
            logger.debug("Wrote %d records to %s", len(records), collection)
        except OSError as e:
            logger.error("Error writing %s: %s", filepath, e)

    def append(self, collection: str, record: dict[str, Any]):
        """Append a single record to a collection."""
        records = self.read_all(collection)
        records.append(record)
        self.write_all(collection, records)

    def find(self, collection: str, **filters) -> list[dict[str, Any]]:
        """
        Find records matching all key=value filters.

        Example: store.find("contacts", name="John")
        """
        records = self.read_all(collection)
        results = []
        for record in records:
            if all(record.get(k) == v for k, v in filters.items()):
                results.append(record)
        return results

    def delete(self, collection: str):
        """Delete an entire collection file."""
        filepath = self._file_path(collection)
        if filepath.exists():
            filepath.unlink()
            logger.info("Deleted collection: %s", collection)
