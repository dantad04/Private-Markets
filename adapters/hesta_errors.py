from __future__ import annotations


class HestaAdapterError(Exception):
    """Base error for the Hesta Stage 1 adapter."""


class HeaderMismatchError(HestaAdapterError):
    pass


class UnknownAssetClassError(HestaAdapterError):
    def __init__(self, row_number: int, value: str, internal_external: str | None = None) -> None:
        detail = f"Unknown asset class at row {row_number}: {value!r}"
        if internal_external:
            detail += f" / {internal_external!r}"
        super().__init__(detail)
        self.row_number = row_number
        self.value = value
        self.internal_external = internal_external


class MalformedRowError(HestaAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class InvalidDateError(HestaAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Invalid date at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class InvalidNumericError(HestaAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class OutOfRangePercentError(HestaAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Out-of-range percent at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class UnexpectedNullTokenError(HestaAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Unexpected null token at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class MultipleOptionsError(HestaAdapterError):
    def __init__(self, observed_options: list[str]) -> None:
        super().__init__(f"Expected one option, observed {observed_options!r}")
        self.observed_options = observed_options


class MultipleDatesError(HestaAdapterError):
    def __init__(self, observed_dates: list[str]) -> None:
        super().__init__(f"Expected one reporting date, observed {observed_dates!r}")
        self.observed_dates = observed_dates


class EmptyFileError(HestaAdapterError):
    pass

