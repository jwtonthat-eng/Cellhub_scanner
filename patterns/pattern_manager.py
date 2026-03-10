"""
Pattern manager: load, save, and manage bill-type regex schemas from patterns.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _resource_path(relative: str) -> Path:
    """Resolve path relative to the app root, compatible with PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
    return base / relative


DEFAULT_PATTERNS_PATH = _resource_path("patterns/patterns.json")

REQUIRED_TOP_LEVEL = {"bill_type", "display_name", "detection_keywords",
                      "row_split_pattern", "columns", "sample_rows"}
REQUIRED_COLUMN = {"name", "display_name", "regex", "capture_group",
                   "default_value", "dtype"}
VALID_DTYPES = {"str", "float", "int", "date"}
VALID_TRANSFORMS = {None, "strip", "upper", "lower", "remove_commas", "remove_spaces"}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ColumnPattern:
    name: str
    display_name: str
    regex: str
    capture_group: int
    default_value: str
    dtype: str
    date_format: str | None = None
    transform: str | None = None
    description: str = ""
    example_match: str = ""


@dataclass
class BillTypeSchema:
    bill_type: str
    display_name: str
    detection_keywords: list[str]
    min_keyword_score: int
    row_split_pattern: str
    columns: list[ColumnPattern]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationError:
    field: str
    message: str
    fatal: bool = True


# ---------------------------------------------------------------------------
# PatternManager
# ---------------------------------------------------------------------------

class PatternManager:
    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_PATTERNS_PATH
        self._data: dict[str, Any] = {"version": "1.0", "bill_types": {}}
        self._schemas: dict[str, BillTypeSchema] = {}
        self.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        if self._path.exists():
            with open(self._path, encoding="utf-8") as fh:
                self._data = json.load(fh)
            self._schemas = {
                k: self._dict_to_schema(k, v)
                for k, v in self._data.get("bill_types", {}).items()
            }

    def save(self) -> None:
        """Atomically write patterns.json (write-then-rename)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = str(self._path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_path, self._path)

    def get_schema(self, bill_type: str) -> BillTypeSchema | None:
        return self._schemas.get(bill_type)

    def all_schemas(self) -> dict[str, BillTypeSchema]:
        return dict(self._schemas)

    def bill_type_names(self) -> list[str]:
        return list(self._schemas.keys())

    def add_bill_type(self, raw_dict: dict[str, Any]) -> tuple[BillTypeSchema, list[ValidationError]]:
        """
        Validate, add, and persist a new bill type from a Gemini response dict.
        Returns the schema and any non-fatal warnings.
        Raises ValueError on fatal validation errors.
        """
        errors = self._validate_raw(raw_dict)
        fatal = [e for e in errors if e.fatal]
        if fatal:
            raise ValueError("; ".join(e.message for e in fatal))

        bill_type = raw_dict["bill_type"]
        # Build the storage dict with defaults for missing optional fields
        storage = {
            "display_name": raw_dict["display_name"],
            "detection_keywords": raw_dict["detection_keywords"],
            "min_keyword_score": raw_dict.get("min_keyword_score", 2),
            "row_split_pattern": raw_dict["row_split_pattern"],
            "columns": raw_dict["columns"],
            "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": "gemini-portal",
                "last_modified": datetime.now(timezone.utc).isoformat(),
                "version": 1,
                "accuracy_score_on_creation": raw_dict.get("_accuracy_score"),
            },
        }
        self._data.setdefault("bill_types", {})[bill_type] = storage
        schema = self._dict_to_schema(bill_type, storage)
        self._schemas[bill_type] = schema
        self.save()
        return schema, [e for e in errors if not e.fatal]

    def update_bill_type(self, bill_type: str, raw_dict: dict[str, Any]) -> None:
        """Replace an existing bill type's column list (used after PatternEditor edits)."""
        if bill_type not in self._data.get("bill_types", {}):
            raise KeyError(f"Bill type '{bill_type}' not found")
        entry = self._data["bill_types"][bill_type]
        entry["columns"] = raw_dict["columns"]
        entry["metadata"]["last_modified"] = datetime.now(timezone.utc).isoformat()
        entry["metadata"]["version"] = entry["metadata"].get("version", 1) + 1
        self._schemas[bill_type] = self._dict_to_schema(bill_type, entry)
        self.save()

    def delete_bill_type(self, bill_type: str) -> None:
        self._data["bill_types"].pop(bill_type, None)
        self._schemas.pop(bill_type, None)
        self.save()

    # ------------------------------------------------------------------
    # Gemini response parsing
    # ------------------------------------------------------------------

    @staticmethod
    def parse_gemini_response(raw_text: str) -> dict[str, Any]:
        """
        Extract and parse JSON from a Gemini chat response.
        Handles markdown code fences and leading/trailing noise.
        Raises ValueError with a descriptive message on failure.
        """
        # Try direct parse
        text = raw_text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strip markdown fences: ```json ... ``` or ``` ... ```
        fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence_match:
            try:
                return json.loads(fence_match.group(1))
            except json.JSONDecodeError:
                pass

        # Find first { to last }
        obj_match = re.search(r"\{.*\}", text, re.DOTALL)
        if obj_match:
            try:
                return json.loads(obj_match.group())
            except json.JSONDecodeError as exc:
                raise ValueError(f"Found JSON-like block but could not parse it: {exc}") from exc

        raise ValueError("No JSON object found in the pasted response. "
                         "Make sure to copy the full Gemini reply.")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_raw(data: dict[str, Any]) -> list[ValidationError]:
        errors: list[ValidationError] = []
        missing_top = REQUIRED_TOP_LEVEL - {"sample_rows"} - set(data.keys())
        for key in missing_top:
            errors.append(ValidationError(key, f"Missing required field: '{key}'", fatal=True))

        if errors:
            return errors

        # Validate row_split_pattern
        try:
            re.compile(data["row_split_pattern"])
        except re.error as exc:
            errors.append(ValidationError(
                "row_split_pattern", f"Invalid regex: {exc}", fatal=True))

        # Validate columns
        for i, col in enumerate(data.get("columns", [])):
            col_label = col.get("name", f"column[{i}]")
            missing = REQUIRED_COLUMN - set(col.keys())
            for key in missing:
                errors.append(ValidationError(
                    f"columns[{i}].{key}",
                    f"Column '{col_label}': missing field '{key}'",
                    fatal=True))
            # Validate regex
            regex = col.get("regex", "")
            if regex:
                try:
                    re.compile(regex)
                except re.error as exc:
                    errors.append(ValidationError(
                        f"columns[{i}].regex",
                        f"Column '{col_label}': invalid regex: {exc}",
                        fatal=False))  # Non-fatal: user can fix in PatternEditorPage
            # Validate dtype
            dtype = col.get("dtype", "str")
            if dtype not in VALID_DTYPES:
                errors.append(ValidationError(
                    f"columns[{i}].dtype",
                    f"Column '{col_label}': unknown dtype '{dtype}', must be one of {VALID_DTYPES}",
                    fatal=False))

        return errors

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dict_to_schema(bill_type: str, d: dict[str, Any]) -> BillTypeSchema:
        columns = [
            ColumnPattern(
                name=c["name"],
                display_name=c.get("display_name", c["name"]),
                regex=c["regex"],
                capture_group=int(c.get("capture_group", 1)),
                default_value=c.get("default_value", ""),
                dtype=c.get("dtype", "str"),
                date_format=c.get("date_format"),
                transform=c.get("transform"),
                description=c.get("description", ""),
                example_match=c.get("example_match", ""),
            )
            for c in d.get("columns", [])
        ]
        return BillTypeSchema(
            bill_type=bill_type,
            display_name=d.get("display_name", bill_type),
            detection_keywords=[kw.lower() for kw in d.get("detection_keywords", [])],
            min_keyword_score=int(d.get("min_keyword_score", 2)),
            row_split_pattern=d.get("row_split_pattern", ""),
            columns=columns,
            metadata=d.get("metadata", {}),
        )
