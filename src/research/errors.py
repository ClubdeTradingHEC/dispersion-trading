# An auditable observation rejection rather than a silent exclusion.

class DataError(ValueError):
    """An auditable observation rejection rather than a silent exclusion."""

    def __init__(self, code, detail=''):
        """Initialize the declared object and retain its explicit dependencies."""
        self.code = code
        self.detail = str(detail)
        super().__init__(f'{code}: {detail}')
