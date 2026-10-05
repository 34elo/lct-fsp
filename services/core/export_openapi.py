#!/usr/bin/env python3
"""Экспортировать OpenAPI схему из приложения."""

import json
import sys

from app.main import app


def main():
    """Export OpenAPI schema to file (stdout redirectable)."""
    schema = app.openapi()
    if schema:
        # Write to stdout with proper encoding
        output = json.dumps(schema, indent=2, ensure_ascii=False)
        sys.stdout.write(output)
        sys.stdout.write("\n")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
