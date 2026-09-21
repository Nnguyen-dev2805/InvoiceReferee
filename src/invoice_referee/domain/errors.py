"""Domain-specific errors raised while accepting a submission."""


class SubmissionValidationError(ValueError):
    """Raised when a submission cannot be accepted for technical reasons."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))
