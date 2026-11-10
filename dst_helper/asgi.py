"""ASGI entry point: python -m uvicorn dst_helper.asgi:app."""
from .server import create_app

app = create_app()
