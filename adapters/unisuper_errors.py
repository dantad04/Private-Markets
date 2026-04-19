from __future__ import annotations


class UniSuperAdapterError(Exception):
    """Base error for the UniSuper state-machine adapter."""


class UniSuperFileIdentityError(UniSuperAdapterError):
    pass


class UniSuperMalformedRowError(UniSuperAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed UniSuper row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class UniSuperUnknownHeaderError(UniSuperAdapterError):
    def __init__(self, row_number: int, header: list[str]) -> None:
        super().__init__(f"Unknown UniSuper header at row {row_number}: {header!r}")
        self.row_number = row_number
        self.header = header


class UniSuperUnknownSectionError(UniSuperAdapterError):
    def __init__(self, row_number: int, section_label: str) -> None:
        super().__init__(f"Unknown UniSuper section at row {row_number}: {section_label!r}")
        self.row_number = row_number
        self.section_label = section_label


class UniSuperInvalidDateError(UniSuperAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Invalid UniSuper reporting date at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class UniSuperInvalidNumericError(UniSuperAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid UniSuper numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value
