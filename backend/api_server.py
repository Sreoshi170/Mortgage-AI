"""Uvicorn launcher for the dedicated backend API."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Mortgage Pre-Check FastAPI backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    uvicorn.run("backend.api:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

