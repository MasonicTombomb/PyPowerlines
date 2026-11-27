"""Tests for the built-in library and the merge rules."""

from __future__ import annotations

import pytest

from pypowerlines.library import Library, builtin_library
from pypowerlines.model import ConductorType


def test_builtin_has_zebra():
    lib = builtin_library()
    c = lib.get_conductor("ACSR Zebra")
    assert c.sub_conductors == 2
    assert c.bundle_spacing_m == pytest.approx(0.4)


def test_builtin_has_sgt():
    lib = builtin_library()
    t = lib.get_transformer("SGT_240MVA_400_132")
    assert t.rating_mva == 240.0
    assert t.hv_kv == 400.0


def test_user_library_overrides_builtin():
    base = builtin_library()
    mine = ConductorType(name="ACSR Zebra", diameter_m=0.028, r20_ohm_per_m=5e-5)
    override = Library(conductors={"ACSR Zebra": mine})
    merged = base.merged_with(override)
    assert merged.get_conductor("ACSR Zebra").r20_ohm_per_m == pytest.approx(5e-5)


def test_missing_key_raises():
    lib = builtin_library()
    with pytest.raises(KeyError):
        lib.get_conductor("Unobtanium")
