from __future__ import annotations


class CbusAdapterError(Exception):
    """Base error for the Cbus Stage 2 late-add adapter."""


class CbusFileIdentityError(CbusAdapterError):
    pass


class CbusHeaderMismatchError(CbusAdapterError):
    pass


class CbusUnknownSectionError(CbusAdapterError):
    def __init__(self, row_number: int, section: str) -> None:
        super().__init__(f"Unknown Cbus section at row {row_number}: {section!r}")
        self.row_number = row_number
        self.section = section


class CbusMalformedRowError(CbusAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed Cbus row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class CbusInvalidDateError(CbusAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Invalid Cbus date at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class CbusInvalidNumericError(CbusAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid Cbus numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class CbusOutOfRangePercentError(CbusAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Out-of-range Cbus percent at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value
