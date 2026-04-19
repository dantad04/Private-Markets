from __future__ import annotations


class SunsuperSchemaAdapterError(Exception):
    """Base error for the shared Sunsuper-schema Stage 2 adapter."""


class HeaderMismatchError(SunsuperSchemaAdapterError):
    pass


class UnknownAssetClassError(SunsuperSchemaAdapterError):
    def __init__(self, row_number: int, value: str, filter_value: str | None) -> None:
        super().__init__(
            f"Unknown asset class at row {row_number}: value={value!r}, filter={filter_value!r}"
        )
        self.row_number = row_number
        self.value = value
        self.filter_value = filter_value


class MalformedRowError(SunsuperSchemaAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class InvalidNumericError(SunsuperSchemaAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class MultipleOptionsError(SunsuperSchemaAdapterError):
    def __init__(self, observed_options: list[str]) -> None:
        super().__init__(f"Expected one option code, observed {observed_options!r}")
        self.observed_options = observed_options


class EmptyFileError(SunsuperSchemaAdapterError):
    pass
