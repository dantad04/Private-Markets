from __future__ import annotations


class ArtQsuperAdapterError(Exception):
    """Base error for the ART-QSuper Stage 2 adapter."""


class HeaderMismatchError(ArtQsuperAdapterError):
    pass


class UnknownAssetClassError(ArtQsuperAdapterError):
    def __init__(self, row_number: int, value: str, internal_external: str | None) -> None:
        super().__init__(
            f"Unknown asset class at row {row_number}: value={value!r}, internal_external={internal_external!r}"
        )
        self.row_number = row_number
        self.value = value
        self.internal_external = internal_external


class MalformedRowError(ArtQsuperAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class InvalidDateError(ArtQsuperAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Invalid date at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class InvalidNumericError(ArtQsuperAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class OutOfRangePercentError(ArtQsuperAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Out-of-range percent at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class MultipleOptionsError(ArtQsuperAdapterError):
    def __init__(self, observed_options: list[str]) -> None:
        super().__init__(f"Expected one option, observed {observed_options!r}")
        self.observed_options = observed_options


class MultipleDatesError(ArtQsuperAdapterError):
    def __init__(self, observed_dates: list[str]) -> None:
        super().__init__(f"Expected one reporting date, observed {observed_dates!r}")
        self.observed_dates = observed_dates


class EmptyFileError(ArtQsuperAdapterError):
    pass
