"""Request helpers shared by views."""


def client_identity(request) -> str:
    """Stable identity for anonymous visitors (guest cart / recently viewed)."""
    return request.headers.get("X-Session-Key", "")[:64]
