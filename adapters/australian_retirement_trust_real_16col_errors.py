from __future__ import annotations


class AustralianRetirementTrustReal16ColumnAdapterError(Exception):
    """Base error for the real Australian Retirement Trust 16-column adapter."""


class EmptyFileError(AustralianRetirementTrustReal16ColumnAdapterError):
    pass


class HeaderMismatchError(AustralianRetirementTrustReal16ColumnAdapterError):
    pass


class SchemaFingerprintMismatchError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(f"Expected schema fingerprint {expected!r}, received {actual!r}")
        self.expected = expected
        self.actual = actual


class UnknownAssetClassError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Unknown ART real 16-column Type at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class MalformedRowError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, row_number: int, reason: str) -> None:
        super().__init__(f"Malformed row {row_number}: {reason}")
        self.row_number = row_number
        self.reason = reason


class InvalidDateError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, row_number: int, value: str) -> None:
        super().__init__(f"Invalid date at row {row_number}: {value!r}")
        self.row_number = row_number
        self.value = value


class UnapprovedReportingPeriodError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, observed_dates: list[str]) -> None:
        super().__init__(f"Expected ART 2025-12-31 reporting date only, observed {observed_dates!r}")
        self.observed_dates = observed_dates


class InvalidNumericError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, row_number: int, column_name: str, value: str) -> None:
        super().__init__(f"Invalid numeric at row {row_number} column {column_name!r}: {value!r}")
        self.row_number = row_number
        self.column_name = column_name
        self.value = value


class MultipleOptionsError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, observed_options: list[str]) -> None:
        super().__init__(f"Expected one option per ART file, observed {observed_options!r}")
        self.observed_options = observed_options


class MultipleDatesError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, observed_dates: list[str]) -> None:
        super().__init__(f"Expected one reporting date per ART file, observed {observed_dates!r}")
        self.observed_dates = observed_dates


class UnexpectedDerivativePostureCountError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, observed_count: int) -> None:
        super().__init__(f"Expected 17 derivative/posture rows in ART file, observed {observed_count}")
        self.observed_count = observed_count


class SourceDomainMismatchError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, source_url: str) -> None:
        super().__init__(
            "ART real 16-column source URL must be under "
            f"'https://files.australianretirementtrust.com.au/phd/super/...'; received {source_url!r}"
        )
        self.source_url = source_url


class FundIdentityMismatchError(AustralianRetirementTrustReal16ColumnAdapterError):
    def __init__(self, fund_code: str) -> None:
        super().__init__(f"ART real 16-column adapter received non-ART fund code {fund_code!r}")
        self.fund_code = fund_code
