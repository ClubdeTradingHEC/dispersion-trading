import wrds


def get_wrds_connection():
    """Create a WRDS connection using credentials from ~/.pgpass."""
    return wrds.Connection(wrds_username="kevinyang4")