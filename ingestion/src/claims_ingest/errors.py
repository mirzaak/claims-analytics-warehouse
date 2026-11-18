"""Errors that carry a message an operator can act on."""


class IngestError(Exception):
    """Base class for expected ingestion failures."""


class ConfigError(IngestError):
    """A setting is missing or invalid."""


class DownloadError(IngestError):
    """A source file could not be downloaded."""


class SourceFormatError(IngestError):
    """A source file does not have the expected structure."""


class LoadError(IngestError):
    """The warehouse rejected a load or returned an unexpected result."""
