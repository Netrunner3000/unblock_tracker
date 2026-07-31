"""Shared configuration loading for the monitor scripts.

All credentials and account identifiers live in a local `.env` file (git-ignored).
Copy `.env.example` to `.env` and fill it in before running any script.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "Copy .env.example to .env and fill it in."
        )
    return value
