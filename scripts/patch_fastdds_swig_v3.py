#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Patch helper for Fast DDS v3 SWIG interface (.i) files.
# Goals (minimal, ordered, idempotent):
#   - Provide only a *forward declaration* of SerializedPayload_t to SWIG via %inline.
#   - Include the real C++ headers inside the %{ %} block (no redefinitions on the SWIG side).
#   - Define required macros in the %{ %} block with #ifndef guards.
#   - Insert additions right after the helper includes (std_*.i / typemaps.i), keeping order stable.

import sys, io, re

if len(sys.argv) != 2:
    print("Usage: patch_fastdds_swig_v3.py <path/to/Generated.i>")
    sys.exit(1)

path = sys.argv[1]
txt = io.open(path, "r", encoding="utf-8").read()
orig = txt

def add_after_anchor(lines):
    """Insert given lines once (skip if already present) right after the last helper %include."""
    global txt
    # Anchor: last occurrence among helper includes (std_*.i / typemaps.i / stdint.i).
    it = list(re.finditer(r'(?m)^\s*%include\s+"(?:std_[a-z]+\.i|typemaps\.i|stdint\.i)"\s*$', txt))
    if it:
        ins = it[-1].end()
    else:
        # Fallback: right after %module if helpers are not found.
        m = re.search(r'(?m)^\s*%module[^\n]*\n', txt)
        ins = m.end() if m else 0
    block = ""
    for ln in lines:
        if ln and ln not in txt:
            block += ln + "\n"
    if block:
        txt = txt[:ins] + "\n" + block + txt[ins:]

# 1) Ensure we have a C++ insertion block %{ %}.
if '%{' not in txt:
    m = re.search(r'(?m)^\s*%module[^\n]*\n', txt)
    pos = m.end() if m else 0
    txt = txt[:pos] + "%{\n%}\n" + txt[pos:]

# 2) In the %{ %} block, add macro guards and real C++ headers (once).
cpp_snippet = r"""/* __FASTDDS_V3_CPP_BLOCK__ */
#ifndef FASTDDS_EXPORTED_API
#define FASTDDS_EXPORTED_API
#endif
#ifndef eProsima_user_DllExport
#define eProsima_user_DllExport
#endif
#include <fastdds/rtps/common/Types.hpp>
#include <fastdds/rtps/history/IPayloadPool.hpp>
#include <fastdds/rtps/common/SerializedPayload.hpp>
using eprosima::fastdds::rtps::octet;
"""
if "/* __FASTDDS_V3_CPP_BLOCK__ */" not in txt:
    txt = re.sub(r'%\}', cpp_snippet + r'\n%}', txt, count=1)

# 3) For SWIG parsing, expose only a *forward declaration* (avoid redefinition in the .i).
#    %inline informs SWIG of the type name; the actual definition comes from the real headers above.
fwd_decl = r"""%inline %{
namespace eprosima { namespace fastdds { namespace rtps {
    struct SerializedPayload_t;
}}}
%}"""
if "struct SerializedPayload_t;" not in txt:
    add_after_anchor([fwd_decl])

# 4) Add missing SWIG helper imports (right after helper includes only).
add_after_anchor([
    '%include <fastcdr/config.h>',
    '%import(module="fastdds") "fastdds/dds/core/LoanableCollection.hpp"',
    '%import(module="fastdds") "fastdds/dds/core/LoanableTypedCollection.hpp"',
    '%import(module="fastdds") "fastdds/dds/core/LoanableSequence.hpp"',
    '%import(module="fastdds") "fastdds/rtps/common/Types.hpp"',
    '%import(module="fastdds") "fastdds/rtps/history/IPayloadPool.hpp"',
    # Do NOT %include the C++ headers here to avoid SWIG-side redefinitions.
    '%include "stdint.i"',
    '%apply unsigned int { eprosima::fastdds::dds::DataRepresentationId_t };',
])

# 5) Add %extend for SerializedPayload_t if not already present.
#    SWIG sees the type via the forward declaration; the definition is provided by the real headers.
if not re.search(r'%extend\s+eprosima::fastdds::rtps::SerializedPayload_t', txt):
    extend = r"""
%extend eprosima::fastdds::rtps::SerializedPayload_t
{
    void bind(uintptr_t addr, uint32_t len)
    {
        $self->data = reinterpret_cast<eprosima::fastdds::rtps::octet*>(addr);
        $self->length = len;
        $self->max_size = len;
        $self->pos = 0;
        $self->encapsulation = 0;
    }
    uintptr_t data_addr() const
    {
        return reinterpret_cast<uintptr_t>($self->data);
    }
}
"""
    # Prefer inserting before the first %include "*.hpp" if present, otherwise append.
    m = re.search(r'(?m)^\s*%include\s+".+?\.hpp"\s*$', txt)
    if m:
        txt = txt[:m.start()] + extend + "\n" + txt[m.start():]
    else:
        txt = txt.rstrip() + "\n" + extend + "\n"

# 5b) Add address conversion helpers for generated message classes.
#     These are used by lwrclpy's optional loaned-message extension to wrap a
#     middleware-loaned sample address back into the concrete SWIG message type.
msg_match = re.search(r'Binding for class\s+([A-Za-z_][A-Za-z_0-9:]*)', txt)
if msg_match and "/* __LWRCLPY_LOAN_ADDR_HELPERS__ */" not in txt:
    fqcn = msg_match.group(1)
    class_name = fqcn.split("::")[-1]
    helper = f'''
/* __LWRCLPY_LOAN_ADDR_HELPERS__ */
%inline %{{
uintptr_t lwrclpy_{class_name}_addr({fqcn}* msg)
{{
    return reinterpret_cast<uintptr_t>(msg);
}}
{fqcn}* lwrclpy_{class_name}_from_addr(uintptr_t addr)
{{
    return reinterpret_cast<{fqcn}*>(addr);
}}
%}}
'''
    include_pat = rf'(?m)^\s*%include\s+"{re.escape(class_name)}\.hpp"\s*$'
    m = re.search(include_pat, txt)
    if m:
        txt = txt[:m.end()] + "\n" + helper + txt[m.end():]
    else:
        txt = txt.rstrip() + "\n" + helper + "\n"

# 5c) Add a per-message DataReader loan wrapper.
#     Fast DDS performs zero-copy receiving through read/take on loanable
#     collections whose max_len is 0, followed by DataReader::return_loan().
#     The wrapper keeps those collections alive while Python inspects samples.
if msg_match and "/* __LWRCLPY_READER_LOAN_HELPERS__ */" not in txt:
    fqcn = msg_match.group(1)
    class_name = fqcn.split("::")[-1]
    loan_cls = f"Lwrclpy_{class_name}_LoanedSamples"
    helper = f'''
/* __LWRCLPY_READER_LOAN_HELPERS__ */
%{{ 
#include <fastdds/dds/core/ReturnCode.hpp>
#include <fastdds/dds/core/LoanableSequence.hpp>
#include <fastdds/dds/subscriber/DataReader.hpp>
#include <fastdds/dds/subscriber/SampleInfo.hpp>

class {loan_cls}
{{
public:
    {loan_cls}()
        : reader_(nullptr)
        , active_(false)
    {{
    }}

    ~{loan_cls}()
    {{
        return_loan();
    }}

    bool take(eprosima::fastdds::dds::DataReader* reader, int32_t max_samples)
    {{
        return read_or_take(reader, max_samples, true);
    }}

    bool read(eprosima::fastdds::dds::DataReader* reader, int32_t max_samples)
    {{
        return read_or_take(reader, max_samples, false);
    }}

    bool return_loan()
    {{
        if (!active_ || reader_ == nullptr)
        {{
            return true;
        }}
        auto ret = reader_->return_loan(data_, infos_);
        active_ = false;
        reader_ = nullptr;
        return ret == eprosima::fastdds::dds::RETCODE_OK;
    }}

    int32_t length() const
    {{
        return static_cast<int32_t>(data_.length());
    }}

    bool active() const
    {{
        return active_;
    }}

    {fqcn}* sample(int32_t index)
    {{
        if (index < 0 || index >= static_cast<int32_t>(data_.length()))
        {{
            return nullptr;
        }}
        return &data_[index];
    }}

    eprosima::fastdds::dds::SampleInfo* info(int32_t index)
    {{
        if (index < 0 || index >= static_cast<int32_t>(infos_.length()))
        {{
            return nullptr;
        }}
        return &infos_[index];
    }}

    bool valid_data(int32_t index) const
    {{
        if (index < 0 || index >= static_cast<int32_t>(infos_.length()))
        {{
            return false;
        }}
        return infos_[index].valid_data;
    }}

private:
    bool read_or_take(eprosima::fastdds::dds::DataReader* reader, int32_t max_samples, bool do_take)
    {{
        return_loan();
        if (reader == nullptr)
        {{
            return false;
        }}
        if (max_samples <= 0)
        {{
            max_samples = -1;
        }}

        eprosima::fastdds::dds::ReturnCode_t ret =
            do_take
                ? reader->take(data_, infos_, max_samples)
                : reader->read(data_, infos_, max_samples);
        if (ret != eprosima::fastdds::dds::RETCODE_OK)
        {{
            return false;
        }}
        reader_ = reader;
        active_ = !data_.has_ownership();
        return data_.length() > 0;
    }}

    eprosima::fastdds::dds::DataReader* reader_;
    eprosima::fastdds::dds::LoanableSequence<{fqcn}> data_;
    eprosima::fastdds::dds::SampleInfoSeq infos_;
    bool active_;
}};
%}}

namespace eprosima {{ namespace fastdds {{ namespace dds {{
    class DataReader;
    struct SampleInfo;
}}}}
}}

class {loan_cls}
{{
public:
    {loan_cls}();
    ~{loan_cls}();
    bool take(eprosima::fastdds::dds::DataReader* reader, int32_t max_samples);
    bool read(eprosima::fastdds::dds::DataReader* reader, int32_t max_samples);
    bool return_loan();
    int32_t length() const;
    bool active() const;
    {fqcn}* sample(int32_t index);
    eprosima::fastdds::dds::SampleInfo* info(int32_t index);
    bool valid_data(int32_t index) const;
}};
'''
    include_pat = rf'(?m)^\s*%include\s+"{re.escape(class_name)}\.hpp"\s*$'
    m = re.search(include_pat, txt)
    if m:
        txt = txt[:m.end()] + "\n" + helper + txt[m.end():]
    else:
        txt = txt.rstrip() + "\n" + helper + "\n"

# 6) Clean up any known bad redefinition blocks (safe pattern).
#    E.g., if someone injected a hand-written "struct SerializedPayload_t { … }" block into the .i, remove it.
txt = re.sub(
    r'(?s)/\* *SWIG-generated SerializedPayload_t start *\*/.*?/\* *SWIG-generated SerializedPayload_t end *\*/',
    '', txt
)

if txt != orig:
    io.open(path, "w", encoding="utf-8", newline="\n").write(txt)
    print(f"[SWIG] patched: {path}")
else:
    print(f"[SWIG] no-change: {path}")
