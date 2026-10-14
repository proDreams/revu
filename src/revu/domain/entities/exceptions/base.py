class CoreException(Exception):
    """Base class for every expected ReVu failure.

    It lives in the domain layer because that is the innermost layer of the
    application: both domain and application code may raise these, and the
    presentation layer can catch them all with a single handler.
    """
