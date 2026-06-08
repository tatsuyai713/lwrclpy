# Windows wheel build

This directory contains the Windows packaging path for `lwrclpy`.

Full build entry point:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/build_all.ps1 `
  -Prefix C:\fast-dds-v3 `
  -GenPrefix C:\fast-dds-gen-v3 `
  -VcpkgRoot C:\vcpkg `
  -VcpkgTriplet x64-windows `
  -BuildRoot ._types_python_build_v3 `
  -PackageVersion 0.5.1
```

This runs:

1. `install_fastdds_v3_vcpkg.ps1`: installs Fast DDS v3/Fast CDR/native dependencies with vcpkg, then builds Fast-DDS-Gen and `fastdds_python`.
2. `gen_python_types.ps1`: runs `fastddsgen -python`, patches SWIG output, and builds generated ROS DataTypes.
3. `make_pip_package_with_runtime.ps1`: stages packages, vendors DLLs, builds a wheel, and repairs it with `delvewheel`.

The Windows build uses vcpkg for the Fast DDS native stack. The default is:

- `VcpkgRoot`: `C:\vcpkg`
- `VcpkgTriplet`: `x64-windows`

`install_fastdds_v3_vcpkg.ps1` bootstraps vcpkg if needed and installs:

- `fastdds`

The `fastdds` port pulls in `fastcdr`, `foonathan-memory`, `asio`, `tinyxml2`, OpenSSL, zlib, and the other native dependencies required by Fast DDS. Use the dynamic `x64-windows` triplet so required DLLs can be copied into the wheel and repaired by `delvewheel`.

Packaging-only entry point:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/make_pip_package_with_runtime.ps1 `
  -BuildRoot ._types_python_build_v3 `
  -FastDdsPrefix C:\fast-dds-v3 `
  -VcpkgRoot C:\vcpkg `
  -VcpkgTriplet x64-windows `
  -PackageVersion 0.5.1
```

Expected inputs:

- `FastDdsPrefix` contains the Windows Fast DDS runtime, Fast CDR runtime, and the `fastdds` Python package for the active Python version.
- `VcpkgRoot\installed\<triplet>` contains the vcpkg-built Fast DDS/Fast CDR CMake packages and runtime DLLs.
- `BuildRoot/src` contains generated ROS DataTypes Python binding build directories for Windows.
- Generated wrapper modules must be Windows binaries (`.pyd` or `.dll`), not Linux `.so` or macOS `.dylib`.

Output:

- Raw wheel: `dist/`
- Repaired Windows wheel with vendored DLLs: `wheelhouse/`

Use `delvewheel` for Windows DLL repair. This is the Windows equivalent of using `auditwheel` on Linux or `delocate` on macOS.

`.github/workflows/build-windows.yml` is a manual workflow that runs the full build on `windows-2022`.
