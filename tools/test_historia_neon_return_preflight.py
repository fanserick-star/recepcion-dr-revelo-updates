"""Offline regression checks for the December Neon return preflight."""
from __future__ import annotations
import importlib.util
from pathlib import Path

path = Path(__file__).with_name("historia_neon_return_preflight.py")
spec = importlib.util.spec_from_file_location("historia_neon_return_preflight", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
c = module.classify

assert c({"a": ("hash", False)}, {})["source_only"] == 1
assert c({}, {"a": ("hash", False)})["destination_only"] == 1
assert c({"a": ("new", False)}, {"a": ("old", False)})["changed"] == 1
assert c({"a": ("new", False)}, {"a": ("old", True)})["reactivation_blockers"] == 1
assert c({"a": ("new", True)}, {"a": ("old", False)})["source_deleted_diff"] == 1
assert c({"a": ("same", False)}, {"a": ("same", False)}) == {
    "source_only": 0, "destination_only": 0,
    "changed": 0, "source_deleted_diff": 0, "reactivation_blockers": 0,
}
assert "IS NOT NULL" in module._expressions("patients", "id", {"id", "name", "deleted_at"})[1]
assert module._expressions("patients", "id", {"id", "name"})[1] == "FALSE"
print("RETURN_TO_OFFICIAL_PREFLIGHT_TESTS_OK")
