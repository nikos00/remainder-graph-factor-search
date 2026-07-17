#!/usr/bin/env python3
from setuptools import Extension, setup

try:
    from Cython.Build import cythonize
except ImportError as exc:
    raise SystemExit(
        "Cython is not installed. Install it first, then run:\n"
        "  python3 setup_dummy_optimized_v5.py build_ext --inplace"
    ) from exc


ext_modules = [
    Extension(
        "dummy_optimized_v5",
        ["dummy_optimized_v5.pyx"],
    )
]


setup(
    name="dummy_optimized_v5",
    ext_modules=cythonize(
        ext_modules,
        compiler_directives={
            "language_level": 3,
            "boundscheck": False,
            "wraparound": False,
            "initializedcheck": False,
            "nonecheck": False,
            "cdivision": True,
            "infer_types": True,
        },
    ),
    zip_safe=False,
)
