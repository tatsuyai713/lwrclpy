# Windows wheel build

This directory contains the Windows packaging path for `lwrclpy`.

Full build entry point:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/build_all.ps1 `
  -BuildWorkRoot C:\lwrclpy_windows_build `
  -VcpkgTriplet x64-windows `
  -BuildArch x64 `
  -PackageVersion 0.5.1
```

This runs:

1. `install_fastdds_v3_vcpkg.ps1`: installs Fast DDS v3/Fast CDR/native dependencies with vcpkg, then builds Fast-DDS-Gen and `fastdds_python`.
2. `gen_python_types.ps1`: runs `fastddsgen -python`, patches SWIG output, and builds generated ROS DataTypes.
3. `make_pip_package_with_runtime.ps1`: stages packages, vendors DLLs, builds a wheel, and repairs it with `delvewheel`.

The Windows build uses vcpkg for the Fast DDS native stack. The default is:

- `BuildWorkRoot`: `C:\lwrclpy_windows_build`
- `VcpkgRoot`: `C:\lwrclpy_windows_build\vcpkg`
- `VcpkgTriplet`: `x64-windows`
- `BuildArch`: `x64`

For Windows ARM64, run on a native Windows ARM64 environment and use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/build_all.ps1 `
  -BuildWorkRoot C:\lwrclpy_windows_build_arm64 `
  -VcpkgTriplet arm64-windows `
  -BuildArch arm64 `
  -PackageVersion 0.5.1
```

`install_fastdds_v3_vcpkg.ps1` bootstraps vcpkg if needed and installs:

- `fastdds`

The `fastdds` port pulls in `fastcdr`, `foonathan-memory`, `asio`, `tinyxml2`, OpenSSL, zlib, and the other native dependencies required by Fast DDS. Use the dynamic `x64-windows` or `arm64-windows` triplet so required DLLs can be copied into the wheel and repaired by `delvewheel`.

During wheel packaging, OpenSSL DLLs are not copied from vcpkg. `make_pip_package_with_runtime.ps1` searches the active Python runtime and Python installations in the GitHub runner tool cache, then vendors Authenticode-valid OpenSSL DLLs whose ABI matches the names expected by the vcpkg-built Fast DDS binaries and whose PE machine type matches the target CPU. The PE header is authoritative because CPython DLL names such as `libssl-3.dll` do not always include an architecture suffix. When a vcpkg dependency expects an architecture-suffixed name, the wheel contains both that alias and the signed DLL's original name so the OpenSSL DLLs' own imports continue to resolve without modifying the signed binaries. The Python 3.10 CI job preloads Python 3.11 into that cache because Python 3.10 ships OpenSSL 1.1 DLLs while Fast DDS is linked against OpenSSL 3. Packaging fails if compatible signed Python `libssl` or `libcrypto` DLLs cannot be found.

Packaging-only entry point:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/windows/make_pip_package_with_runtime.ps1 `
  -BuildWorkRoot C:\lwrclpy_windows_build `
  -VcpkgTriplet x64-windows `
  -BuildArch x64 `
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

## DataSharing / loaned-message status

Windows wheels keep Fast DDS normal publish/subscribe enabled, but disable the automatic DataSharing/loaned-message path by default.

This is a correctness guard, not a placeholder. The Windows generated bindings are split across many package-local `.dll`/`.pyd` files. The experimental loan path uses `lwrclpy_loan_sample_addr()` and `lwrclpy_<Type>_from_addr()` to reinterpret a middleware-loaned raw address as a generated Python/SWIG message. On Windows this can cross generated-DLL boundaries incorrectly. In local verification, publishing `geometry_msgs/msg/Point` through the automatic loan path entered a different geometry message setter and terminated the process with a native access violation instead of raising a Python exception.

Because that failure is process-fatal, Windows defaults to the regular `DataWriter.write(msg)` path for `publish(msg)`. Do not enable Windows DataSharing in CI until the raw-address loan helper is made type-safe for the Windows generated DLL layout. For debugging that specific path only, set:

```powershell
$env:LWRCLPY_ENABLE_WINDOWS_DATASHARING = "1"
```

The explicit opt-in is intentionally unsafe and should not be used for normal wheel validation.

`.github/workflows/build-windows.yml` is a manual workflow that runs the full x64 build on `windows-2022` and the ARM64 build on GitHub's `windows-11-arm` hosted runner. The ARM64 GitHub runner label is available for public repositories; private repositories need a compatible larger or self-hosted ARM64 Windows runner.
