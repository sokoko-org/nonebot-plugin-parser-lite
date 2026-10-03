"""Bilibili helpers and the generated protobuf namespace."""

import importlib
import sys

# The generated files use the top-level ``bilibili`` import emitted by protoc.
# Expose the bundled namespace before any generated module is imported.
_generated = importlib.import_module(".bilibili", __name__)
sys.modules.setdefault("bilibili", _generated)

