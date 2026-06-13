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


def add_primitive_sequence_buffer_fast_paths():
    """Add buffer-oriented helpers for primitive std::vector<T> fields.

    fastddsgen's default SWIG conversion builds std::vector<uint8_t> through the
    generic sequence path.  For ROS fields such as sensor_msgs/Image.data and
    sensor_msgs/PointCloud2.data this is the dominant Python-side cost.  The
    generated overloads below accept Python buffer objects and copy them into
    C++ vectors with a single resize+memcpy.  They also expose writable
    memoryviews so users can fill large ROS-compatible sequence fields in place.
    """
    global txt
    if "/* __LWRCLPY_PRIMITIVE_SEQUENCE_BUFFER_FAST_PATHS__ */" in txt:
        return

    msg_match_local = re.search(r'Binding for class\s+([A-Za-z_][A-Za-z_0-9:]*)', txt)
    if not msg_match_local:
        return
    fqcn = msg_match_local.group(1)
    class_name = fqcn.split("::")[-1]

    primitive_types = {
        "uint8_t": "uint8_t",
        "octet": "uint8_t",
        "unsignedchar": "uint8_t",
        "int8_t": "int8_t",
        "char": "char",
        "uint16_t": "uint16_t",
        "unsignedshort": "uint16_t",
        "int16_t": "int16_t",
        "short": "int16_t",
        "uint32_t": "uint32_t",
        "unsignedint": "uint32_t",
        "unsignedlong": "uint32_t",
        "int32_t": "int32_t",
        "int": "int32_t",
        "long": "int32_t",
        "uint64_t": "uint64_t",
        "unsignedlonglong": "uint64_t",
        "int64_t": "int64_t",
        "longlong": "int64_t",
        "float": "float",
        "double": "double",
    }

    fields: list[tuple[str, str]] = []
    seen_fields: set[str] = set()
    for match in re.finditer(
        rf'%ignore\s+{re.escape(fqcn)}::([A-Za-z_][A-Za-z_0-9]*)'
        r'\(\s*std::vector\s*<\s*([^>]+?)\s*>\s*&&\s*\)\s*;',
        txt,
    ):
        name = match.group(1)
        raw_type = match.group(2)
        key = re.sub(r'\s+', '', raw_type)
        ctype = primitive_types.get(key)
        if ctype is None or name in seen_fields:
            continue
        seen_fields.add(name)
        fields.append((name, ctype))
    if not fields:
        return

    methods = []
    ignore_lines = []
    for field, ctype in fields:
        ignore_lines.append(f'%ignore {fqcn}::{field}(const std::vector<{ctype}>&);')
        methods.append(f'''
    void {field}(PyObject* obj)
    {{
        Py_buffer view;
        if (PyObject_GetBuffer(obj, &view, PyBUF_CONTIG_RO) == 0)
        {{
            if (view.len < 0)
            {{
                PyBuffer_Release(&view);
                throw std::runtime_error("negative buffer size");
            }}
            if ((static_cast<size_t>(view.len) % sizeof({ctype})) != 0)
            {{
                PyBuffer_Release(&view);
                throw std::runtime_error("buffer size is not aligned to sequence element size");
            }}
            std::vector<{ctype}> tmp;
            tmp.resize(static_cast<size_t>(view.len) / sizeof({ctype}));
            if (view.len > 0)
            {{
                std::memcpy(
                    reinterpret_cast<void*>(tmp.data()),
                    view.buf,
                    static_cast<size_t>(view.len));
            }}
            PyBuffer_Release(&view);
            self->{field}(std::move(tmp));
            return;
        }}
        PyErr_Clear();

        std::vector<{ctype}>* ptr = nullptr;
        int res = swig::asptr(obj, &ptr);
        if (!SWIG_IsOK(res) || ptr == nullptr)
        {{
            throw std::runtime_error("expected a bytes-like object or compatible std::vector");
        }}
        self->{field}(*ptr);
        if (SWIG_IsNewObj(res))
        {{
            delete ptr;
        }}
    }}

    PyObject* _lwrclpy_{field}_bytes()
    {{
        const auto& value = self->{field}();
        const char* data = value.empty()
            ? ""
            : reinterpret_cast<const char*>(value.data());
        return PyBytes_FromStringAndSize(
            data,
            static_cast<Py_ssize_t>(value.size() * sizeof({ctype})));
    }}

    PyObject* _lwrclpy_{field}_memoryview()
    {{
        static char empty = 0;
        auto& value = self->{field}();
        char* data = value.empty()
            ? &empty
            : reinterpret_cast<char*>(value.data());
        return PyMemoryView_FromMemory(
            data,
            static_cast<Py_ssize_t>(value.size() * sizeof({ctype})),
            PyBUF_WRITE);
    }}

    void _lwrclpy_{field}_resize(size_t size)
    {{
        auto value = self->{field}();
        value.resize(size);
        self->{field}(std::move(value));
    }}

    size_t _lwrclpy_{field}_size()
    {{
        const auto& value = self->{field}();
        return value.size();
    }}

    size_t _lwrclpy_{field}_nbytes()
    {{
        const auto& value = self->{field}();
        return value.size() * sizeof({ctype});
    }}
''')

    helper = f'''
/* __LWRCLPY_PRIMITIVE_SEQUENCE_BUFFER_FAST_PATHS__ */
%{{
#include <cstring>
#include <cstdint>
#include <stdexcept>
%}}
{chr(10).join(ignore_lines)}
%extend {fqcn}
{{
{''.join(methods)}
}}
'''

    include_pat = rf'(?m)^\s*%include\s+"{re.escape(class_name)}\.hpp"\s*$'
    m = re.search(include_pat, txt)
    if m:
        txt = txt[:m.start()] + helper + "\n" + txt[m.start():]
    else:
        txt = txt.rstrip() + "\n" + helper + "\n"

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

# 5d) Add generic fast paths for large primitive sequence fields.
add_primitive_sequence_buffer_fast_paths()

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
