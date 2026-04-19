from __future__ import annotations


class HostPlusAdapterError(Exception):
    """Base error for the Host-Plus state-machine adapter."""


class HostPlusFileIdentityError(HostPlusAdapterError):
    pass


class HostPlusMalformedRowError(HostPlusAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed Host-Plus row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class HostPlusUnknownHeaderError(HostPlusAdapterError):
    def __init__(self, row_number: int, header: list[str]) -> None:
        super().__init__(f"Unknown Host-Plus header at row {row_number}: {header!r}")
        self.row_number = row_number
        self.header = header


class HostPlusUnknownSectionError(HostPlusAdapterError):
    def __init__(self, row_number: int, section_label: str) -> None:
        super().__init__(f"Unknown Host-Plus section at row {row_number}: {section_label!r}")
        self.row_number = row_number
        self.section_label = section_label


class HostPlusInvalidNumericError(HostPlusAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid Host-Plus numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value
