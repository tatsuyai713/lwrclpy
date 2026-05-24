#!/usr/bin/env python3
"""Patch Fast-DDS-python SWIG interfaces with lwrclpy loan helpers.

The upstream Python binding exposes DataWriter.loan_sample(void*&), which is not
usable from Python because callers cannot pass a mutable C++ void* reference.
This patch adds address-based helpers that lwrclpy can use after rebuild:

- DataWriter.lwrclpy_loan_sample_addr(kind) -> uintptr_t
- DataWriter.lwrclpy_write_addr(addr) -> bool

Generated message bindings are patched separately by patch_fastdds_swig_v3.py to
add lwrclpy_<Msg>_from_addr(addr), giving Python a typed message wrapper around
the loaned address.
"""

from __future__ import annotations

import io
import os
import platform
import sys


HELPER = r'''

/* __LWRCLPY_DATAWRITER_LOAN_HELPERS__ */
%include "stdint.i"
%{
#include <cstdint>
#include <fastdds/dds/core/ReturnCode.hpp>
%}

%extend eprosima::fastdds::dds::DataWriter
{
    uintptr_t lwrclpy_loan_sample_addr(int initialization_kind = 0)
    {
        void* sample = nullptr;
        auto kind = static_cast<eprosima::fastdds::dds::DataWriter::LoanInitializationKind>(initialization_kind);
        auto ret = $self->loan_sample(sample, kind);
        if (ret != eprosima::fastdds::dds::RETCODE_OK || sample == nullptr)
        {
            return 0;
        }
        return reinterpret_cast<uintptr_t>(sample);
    }

    bool lwrclpy_write_addr(uintptr_t addr)
    {
        if (addr == 0)
        {
            return false;
        }
        return $self->write(reinterpret_cast<void*>(addr)) == eprosima::fastdds::dds::RETCODE_OK;
    }
}
'''


def should_patch(text: str) -> bool:
    return (
        "DataWriter" in text
        and "loan_sample" in text
        and "eprosima::fastdds::dds::DataWriter" in text
        and "__LWRCLPY_DATAWRITER_LOAN_HELPERS__" not in text
    )


def patch_file(path: str) -> bool:
    with io.open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    if not should_patch(text):
        return False
    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip() + "\n" + HELPER + "\n")
    print(f"[loan-helper] patched: {path}")
    return True


def patch_macos_uint64_vector(path: str) -> bool:
    if platform.system() != "Darwin" or os.path.basename(path) != "fastdds.i":
        return False

    with io.open(path, "r", encoding="utf-8") as handle:
        text = handle.read()

    old = "%template(uint64_t_vector) std::vector<uint64_t>;"
    new = "%template(uint64_t_vector) std::vector<unsigned long long>;"
    if old not in text or new in text:
        return False

    with io.open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(old, new))
    print(f"[mac-uint64] patched: {path}")
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <Fast-DDS-python source root or workspace src>", file=sys.stderr)
        return 2
    root = sys.argv[1]
    patched = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith(".i"):
                try:
                    patched += int(patch_file(os.path.join(dirpath, filename)))
                    patched += int(patch_macos_uint64_vector(os.path.join(dirpath, filename)))
                except UnicodeDecodeError:
                    pass
    print(f"[loan-helper] patched files: {patched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())