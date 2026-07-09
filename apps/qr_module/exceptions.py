"""
AKHU AFIVS — Custom Exceptions for QR Module and Permits
"""

class PermitNotReleasedError(Exception):
    """Raised when trying to access or render a permit before it has been released/generated."""
    pass
