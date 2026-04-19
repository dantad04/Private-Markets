from __future__ import annotations


class AwareAdapterError(Exception):
    """Base error for the Aware Stage 2 adapter."""


class HeaderMismatchError(AwareAdapterError):
    pass


class InvalidScheduleHeaderError(AwareAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Invalid schedule header at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class UnknownAssetClassError(AwareAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Unknown asset class at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class MalformedRowError(AwareAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class InvalidDateError(AwareAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Invalid date at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class InvalidNumericError(AwareAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class OutOfRangePercentError(AwareAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Out-of-range percent at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class MultipleOptionsError(AwareAdapterError):
    def __init__(self, observed_options: list[str]) -> None:
        super().__init__(f"Expected one option, observed {observed_options!r}")
        self.observed_options = observed_options


class MultipleDatesError(AwareAdapterError):
    def __init__(self, observed_dates: list[str]) -> None:
        super().__init__(f"Expected one reporting date, observed {observed_dates!r}")
        self.observed_dates = observed_dates


class EmptyFileError(AwareAdapterError):
    pass
