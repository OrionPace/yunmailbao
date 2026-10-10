# Third-Party Notices

Copyright (C) 2026 YunYouBao contributors.

SPDX-License-Identifier for YunYouBao's original code: GPL-3.0-only.
The project's LICENSE is the unmodified GNU General Public License version 3
text. Third-party copyrights, licenses, exceptions and notices remain their
owners' terms; they are not replaced by the project's GPL designation.

## Audit Scope And Evidence

This inventory was checked on 2026-10-10 against uv.lock, the installed Windows
x64 environment and the original candidate (now built in .build/candidate/YunYouBao). All 43 installed Python
distributions match their locked versions. The candidate contains 154 DLL/PYD
files (68 BINARY and 86 EXTENSION entries); all match the SHA-256 of their
COLLECT-00.toc source files. The 80 native files sourced from installed Python
distributions also match their wheel RECORD hashes. This is provenance evidence,
not a blanket redistribution-compliance declaration or native execution test.
A package listed below is not necessarily included in the executable.

Original texts are retained under packaging/licenses, with relative paths,
origins and SHA-256 digests in
[license-sources.json](packaging/licenses/license-sources.json).
Inside the frozen application's _internal directory, the same tree is available
as packaging/licenses/. Preserve that complete tree when redistributing the application.
The table links are relative to this notice in both layouts. Copyright and attribution
statements are in the linked original texts, including all accompanying notices.

Local dist-info texts were copied byte-for-byte, including files omitted from
wheel RECORD entries. No generic SPDX template was substituted for an author's
license. Missing pythonnet/clr-loader texts were taken from official PyPI source
archives of the exact locked versions, after checking their uv.lock SHA-256.
OpenSSL's local package cache has no license copy; its text and authors list were
taken from the official openssl-3.5.4 tag, while the local conda metadata and
openssl version command both identify 3.5.4. These sources are recorded in the
index. The index now covers 102 original texts, including exact-version official
SDK and vendored-component originals added during candidate review. Conda-cache
license copies are byte-for-byte; archive digests for those copies are recorded
from installed conda metadata, not a fresh archive-download verification.
For cffi's embedded libffi, complete original leading copyright/license comments
are extracted byte-for-byte from the hash-checked 2.0.0 source archive, rather
than inventing a separate license file. This snapshot must be refreshed if the
lock, interpreter, tool or candidate binaries change.

## Runtime Python Dependencies

The identifiers below summarize metadata and supplied texts, not additional
permissions. Compound licenses and exceptions must be read in the originals.
Each link points to a retained original text; adjacent AUTHORS or additional
license files in the same component directory are also part of the notices.

| Component | Version | License evidence | Original text |
| --- | --- | --- | --- |
| annotated-doc | 0.0.4 | MIT | [LICENSE](packaging/licenses/annotated-doc-0.0.4/licenses/LICENSE) |
| annotated-types | 0.7.0 | MIT | [LICENSE](packaging/licenses/annotated-types-0.7.0/licenses/LICENSE) |
| anyio | 4.13.0 | MIT | [LICENSE](packaging/licenses/anyio-4.13.0/licenses/LICENSE) |
| bottle | 0.13.4 | MIT | [LICENSE](packaging/licenses/bottle-0.13.4/licenses/LICENSE) |
| cffi | 2.0.0 | Metadata MIT; supplied text says MIT No Attribution (MIT-0); AUTHORS retained | [LICENSE](packaging/licenses/cffi-2.0.0/licenses/LICENSE) |
| click | 8.3.1 | BSD-3-Clause | [LICENSE.txt](packaging/licenses/click-8.3.1/licenses/LICENSE.txt) |
| clr_loader | 0.2.10 | MIT; exact-version source-archive text | [LICENSE](packaging/licenses/clr-loader-0.2.10/LICENSE) |
| colorama | 0.4.6 | BSD-3-Clause, verified from supplied text | [LICENSE.txt](packaging/licenses/colorama-0.4.6/licenses/LICENSE.txt) |
| et_xmlfile | 2.0.0 | MIT plus incorporated Python terms; AUTHORS retained | [LICENCE.rst](packaging/licenses/et-xmlfile-2.0.0/LICENCE.rst), [LICENCE.python](packaging/licenses/et-xmlfile-2.0.0/LICENCE.python) |
| FastAPI | 0.135.3 | MIT | [LICENSE](packaging/licenses/fastapi-0.135.3/licenses/LICENSE) |
| h11 | 0.16.0 | MIT | [LICENSE.txt](packaging/licenses/h11-0.16.0/licenses/LICENSE.txt) |
| idna | 3.11 | BSD-3-Clause | [LICENSE.md](packaging/licenses/idna-3.11/licenses/LICENSE.md) |
| Jinja2 | 3.1.6 | BSD-3-Clause, verified from supplied text | [LICENSE.txt](packaging/licenses/jinja2-3.1.6/licenses/LICENSE.txt) |
| MarkupSafe | 3.0.3 | BSD-3-Clause | [LICENSE.txt](packaging/licenses/markupsafe-3.0.3/licenses/LICENSE.txt) |
| NumPy | 2.4.4 | Metadata: BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0; binary-distribution and per-component terms retained, see below | [combined LICENSE.txt](packaging/licenses/numpy-2.4.4/licenses/LICENSE.txt) |
| openpyxl | 3.1.5 | MIT | [LICENCE.rst](packaging/licenses/openpyxl-3.1.5/LICENCE.rst) |
| pandas | 3.0.2 | BSD-3-Clause for pandas; exact-version upstream vendored notices also retained | [LICENSE](packaging/licenses/pandas-3.0.2/LICENSE), [vendored notices](packaging/licenses/pandas-3.0.2/LICENSES/) |
| proxy-tools | 0.1.0 | Metadata MIT conflicts with BSD source header and upstream BSD-2-Clause text; release-owner review required | [original LICENSE.txt](packaging/licenses/proxy-tools-0.1.0/LICENSE.txt) |
| pycparser | 3.0 | BSD-3-Clause | [LICENSE](packaging/licenses/pycparser-3.0/licenses/LICENSE) |
| Pydantic | 2.12.5 | MIT | [LICENSE](packaging/licenses/pydantic-2.12.5/licenses/LICENSE) |
| pydantic-core | 2.41.5 | MIT; embedded native/vendor dependencies still need candidate review | [LICENSE](packaging/licenses/pydantic-core-2.41.5/licenses/LICENSE) |
| python-dateutil | 2.9.0.post0 | Apache-2.0 and BSD-3-Clause terms apply to the contributions described in the supplied text | [LICENSE](packaging/licenses/python-dateutil-2.9.0.post0/LICENSE) |
| python-dotenv | 1.2.2 | BSD-3-Clause | [LICENSE](packaging/licenses/python-dotenv-1.2.2/licenses/LICENSE) |
| python-multipart | 0.0.22 | Apache-2.0 | [LICENSE.txt](packaging/licenses/python-multipart-0.0.22/licenses/LICENSE.txt) |
| pythonnet | 3.0.5 | MIT; exact-version source-archive LICENSE and AUTHORS retained; embedded nullability attributes have an additional MIT notice below | [LICENSE](packaging/licenses/pythonnet-3.0.5/LICENSE), [AUTHORS.md](packaging/licenses/pythonnet-3.0.5/AUTHORS.md) |
| pywebview | 6.1 | BSD-3-Clause for pywebview itself, not a blanket license for Microsoft SDK binaries | [LICENSE](packaging/licenses/pywebview-6.1/licenses/LICENSE) |
| six | 1.17.0 | MIT | [LICENSE](packaging/licenses/six-1.17.0/LICENSE) |
| Starlette | 1.0.0 | BSD-3-Clause | [LICENSE.md](packaging/licenses/starlette-1.0.0/licenses/LICENSE.md) |
| typing_extensions | 4.15.0 | Metadata PSF-2.0; full supplied Python historical notices retained | [LICENSE](packaging/licenses/typing-extensions-4.15.0/licenses/LICENSE) |
| typing-inspection | 0.4.2 | MIT | [LICENSE](packaging/licenses/typing-inspection-0.4.2/licenses/LICENSE) |
| tzdata | 2025.3 | Apache-2.0; accompanying full Apache text retained | [LICENSE](packaging/licenses/tzdata-2025.3/licenses/LICENSE), [LICENSE_APACHE](packaging/licenses/tzdata-2025.3/licenses/licenses/LICENSE_APACHE) |
| Uvicorn | 0.42.0 | BSD-3-Clause | [LICENSE.md](packaging/licenses/uvicorn-0.42.0/licenses/LICENSE.md) |

The proxy-tools source archive was hash-checked against uv.lock; its module
copyright header explicitly describes BSD licensing. Its LICENSE.txt was
missing from both the installed wheel and source archive, so the original was
retrieved from the official upstream
[2014-05-05 pre-release commit](https://github.com/jtushman/proxy_tools/blob/ccd35a569b95bec271a59890780c7821756c548a/LICENSE.txt).
It credits Armin Ronacher and Jonathan Tushman. Its wording, including the
original trailing text, is preserved without repair. This is an evidence
discrepancy, not a claim that the package has been relicensed. Specifically, the
installed METADATA says `License: MIT` and has an MIT classifier, while the
installed module says `:license: BSD, see LICENSE for more details.` The cited
upstream commit itself also says MIT in setup.py while supplying BSD-2-Clause
LICENSE.txt. No upstream correction or exact-release MIT grant was obtained in
this audit. Both observations remain recorded; the BSD original is preserved,
and this component is not marked as unambiguously MIT or fully resolved.

## Interpreter And OpenSSL

| Component | Observed source/version | License evidence | Original text |
| --- | --- | --- | --- |
| CPython | conda-forge Python 3.12.12, h0159041_1_cpython | Conda metadata Python-2.0; full PSF, historical and incorporated terms as supplied | [LICENSE_PYTHON.txt](packaging/licenses/cpython-3.12.12/LICENSE_PYTHON.txt) |
| OpenSSL | conda-forge OpenSSL 3.5.4, h725018a_0; libcrypto-3-x64.dll and libssl-3-x64.dll | Apache-2.0, confirmed by package metadata and exact-version upstream text; authors retained | [LICENSE.txt](packaging/licenses/openssl-3.5.4/LICENSE.txt), [AUTHORS.md](packaging/licenses/openssl-3.5.4/AUTHORS.md) |

The interpreter's original license was copied from its installed
LICENSE_PYTHON.txt, not replaced with a current-version web template. This
packaging work does not modify CPython or OpenSSL implementation code.
The spec retains DLL matching against sys.base_prefix. A later build using
another CPython distribution or newer 3.12 patch release must retain that
interpreter's actual license and any separately redistributed libraries.
These two OpenSSL notices do not grant permissions for other DLLs found in the
interpreter directory.

## Build, Test And Potentially Collected Dependencies

These packages are installed by the locked development environment. Their
notices are included conservatively; inspect the candidate before describing
them as application payload. Pillow may be collected despite being declared a
development dependency. HTTPX is used for tests, not real SMTP delivery.

| Component | Version | License evidence | Original text |
| --- | --- | --- | --- |
| altgraph | 0.17.5 | MIT | [LICENSE](packaging/licenses/altgraph-0.17.5/LICENSE) |
| certifi | 2026.7.22 | MPL-2.0 | [LICENSE](packaging/licenses/certifi-2026.7.22/licenses/LICENSE) |
| httpcore | 1.0.9 | BSD-3-Clause | [LICENSE.md](packaging/licenses/httpcore-1.0.9/licenses/LICENSE.md) |
| HTTPX | 0.28.1 | BSD-3-Clause | [LICENSE.md](packaging/licenses/httpx-0.28.1/licenses/LICENSE.md) |
| packaging | 26.0 | Apache-2.0 OR BSD-2-Clause; both originals retained | [LICENSE](packaging/licenses/packaging-26.0/licenses/LICENSE), [Apache](packaging/licenses/packaging-26.0/licenses/LICENSE.APACHE), [BSD](packaging/licenses/packaging-26.0/licenses/LICENSE.BSD) |
| pefile | 2024.8.26 | MIT | [LICENSE](packaging/licenses/pefile-2024.8.26/LICENSE) |
| Pillow | 12.2.0 | MIT-CMU for Pillow/PIL plus the bundled library notices in its full binary-distribution text | [combined LICENSE](packaging/licenses/pillow-12.2.0/licenses/LICENSE) |
| PyInstaller | 6.19.0 | GPL-2.0-or-later with original Bootloader Exception; embedded runtime hooks Apache-2.0 | [COPYING.txt](packaging/licenses/pyinstaller-6.19.0/licenses/COPYING.txt) |
| pyinstaller-hooks-contrib | 2026.4 | Standard hooks GPL-2.0-or-later; runtime hooks Apache-2.0 | [LICENSE](packaging/licenses/pyinstaller-hooks-contrib-2026.4/licenses/LICENSE) |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause | [LICENSE.txt](packaging/licenses/pywin32-ctypes-0.2.3/LICENSE.txt) |
| setuptools | 82.0.1 | MIT; spec excludes setuptools from application analysis | [LICENSE](packaging/licenses/setuptools-82.0.1/licenses/LICENSE) |
| Inno Setup | 7.1.0 x64 | Original Inno Setup License; toolchain not copied into application, generated setup runtime remains third-party code | [license.txt](packaging/licenses/inno-setup-7.1.0/license.txt) |

PyInstaller's copied COPYING.txt retains the complete Bootloader Exception,
not just the GPL text. The exception covers the compiled bootloader and related
embedded files described there; it is not a waiver for every Python dependency.
The same file retains its Apache runtime-hook terms, full GPL/Apache texts and
additional isolated-submodule MIT terms. The community-hooks notice separately
distinguishes build hooks from embedded runtime hooks.

Inno Setup is copyright Jordan Russell, with portions copyright Martijn Laan.
The unmodified installed tool license is retained. Its compiler currently
reports "Non-commercial use only"; the release owner must verify any commercial
tool-use entitlement separately. No YunYouBao code-signing claim is made.

## Bundled Library Notices Must Remain Intact

NumPy's combined binary-distribution LICENSE.txt identifies OpenBLAS, LAPACK
and GCC runtime code and retains their respective terms, including
GPL-3.0-or-later WITH GCC-exception-3.1. Its full per-component license directory
is also copied, including libdivide, pythoncapi-compat, Highway, Dragon4,
x86-simd-sort, SVML, pocketfft, lapack_lite and random-generator notices.
The main NumPy metadata expression is not an exhaustive license label for every
DLL. In particular, it does not clear the separate msvcp140 DLL.

Pillow's complete supplied LICENSE retains PIL/Pillow copyrights and all its
bundled-library notices, including FreeType and its separate terms. These
notices must not be collapsed into a generic MIT or MIT-CMU template.
Certifi's MPL-2.0 text is preserved; if its covered files are redistributed,
retain the applicable source-availability information as well as the license.

## Frontend Vendor Notices

The frontend references local static/vendor/quill.min.js, quill.snow.css and
lucide.min.js. The original vendor notices are supplied in that same tree:

| Observed asset header | Supplied notice | Audit boundary |
| --- | --- | --- |
| Quill Editor 1.3.6 | [Quill BSD-3-Clause text](static/vendor/quill.LICENSE.txt), retaining Jason Chen and salesforce.com copyrights | JS, CSS and LICENSE byte-identical to official npm 1.3.6 package |
| Lucide 0.468.0 | [Lucide ISC text](static/vendor/lucide.LICENSE.txt), including its Feather/MIT attribution | UMD JS and complete supplied LICENSE byte-identical to official npm 0.468.0 package |

These frontend originals are already included by the spec's static datas entry;
they have not been replaced or copied into packaging/licenses by this audit.
The license-sources.json hashes cover the 102 texts in packaging/licenses, not
these separate frontend files. Preserve the supplied files in the shipped
static/vendor tree. Both npm archives were checked against their registry
SHA-512 integrity fields, then the actual assets and originals were compared:

* [quill-1.3.6.tgz](https://registry.npmjs.org/quill/-/quill-1.3.6.tgz): archive
  SHA-256 `f75a1098bdfe22766be958c77e53a10b73107abb50b2f11cdcce914288fcf167`;
  quill.min.js `de86018869b5e845bdc101fc1b55611a1e375e08af6cee4a681d7446103da611`;
  quill.snow.css `892e299431955e9ae388ae257f72024ee76af2d52a7a97a868f70fbe50f16144`;
  quill.LICENSE.txt `0213df747bcdd0aba14b8cc4d9b57d1db2fee16fa74539a73a11b11570767e76`.
* [lucide-0.468.0.tgz](https://registry.npmjs.org/lucide/-/lucide-0.468.0.tgz): archive
  SHA-256 `cab2924552d273da12de0beab51d81ef2e2d397b0ac0eef010eaa02fd4ae5764`;
  lucide.min.js `3411692820cb8d47543f69496aa25fd603a358f4498046f41c508a5a3342210e`;
  lucide.LICENSE.txt `1e7290b35280a048667bbf0ebabac1c7fd52a75300e8b2946ac165715997f2bc`.

No frontend vendor asset or original notice was modified by this audit.

## Candidate Native Binary Evidence

Paths here are relative to the candidate's _internal directory. Build metadata
in release/0.2.0/build-manifest.json records every payload file's size and SHA-256;
the PyInstaller source mapping is in .build/work/auto_email/COLLECT-00.toc.
The interpreter root for this audit is D:/Apps/Miniforge3. Binary equality does
not mean a reproducible source rebuild or satisfaction of every license condition.

### Microsoft WebView2 SDK And Interop

The official [Microsoft NuGet package 1.0.2957.106](https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.2957.106)
has SHA-256 `4c35a54835b63954159eac1d5b7a60ae617a41dbb5b73bfdb11c4870a891080a`.
Its nuspec designates LICENSE.txt as the license. The original Microsoft
BSD-3-Clause [LICENSE.txt](packaging/licenses/microsoft-web-webview2-1.0.2957.106/LICENSE.txt)
and accompanying [NOTICE.txt](packaging/licenses/microsoft-web-webview2-1.0.2957.106/NOTICE.txt)
are retained separately from pywebview's BSD notice. The SDK's NOTICE identifies
ANTLR/StringTemplate tool components; retaining that whole notice does not claim
their DLLs are in this candidate. None of the package's tools/wv2winrt DLLs or
WPF/Projection DLLs are shipped here.

| Actual candidate file | Exact-version official package match (SHA-256) |
| --- | --- |
| webview/lib/Microsoft.Web.WebView2.Core.dll | lib/net462 counterpart: `cb8c852fcc4ef55d630b64d171dc11538bb25258041ed22cf31735982a2e09e3` |
| webview/lib/Microsoft.Web.WebView2.WinForms.dll | lib/net462 counterpart: `e62056bee28ab094071144b47371009a6fbc162f9aea184719f2e86ed515f7f8` |
| webview/lib/runtimes/win-x64/native/WebView2Loader.dll | Same NuGet path: `271b57e3ec03c436a15d80cafeb9fd1618a43793233d8b05c9446f8de0a51be4` |
| webview/lib/runtimes/win-x86/native/WebView2Loader.dll | Same NuGet path: `7f362fd98cc243ad620f2d0a4a6c223df80f960c4e19a2d9972f4af7938565cf` |
| webview/lib/runtimes/win-arm64/native/WebView2Loader.dll | Same NuGet path: `277e84cd9474ef6302ff3bc91706ccac9bc709cd226de4dbd7dad28571b2bc05` |

All five file-version resources say 1.0.2957.106. Both non-x64 loaders are
actually collected by pywebview's hook, not merely present in the environment.
The separate Evergreen Runtime is not bundled.

The two WebBrowserInterop DLLs match the official
[pywebview 6.1 tree](https://github.com/r0x0r/pywebview/tree/6.1/interop/mshtml):
x64 Git blob `a4d0a1fadb2d01109822ef04bdee68f36705f924`, SHA-256
`f6a646470f0e1058224a52e8e2e217501dca46939b30bfc9a5dd4dcdd43f088d`;
x86 Git blob `4c73b8f5069d49155e320cef2c4f13ebf022cafb`, SHA-256
`4e527297fbea7c5a0419f3a6af307c2681787beb0bf0ef3fea849a7fd85a08dc`.
The official csproj compiles the repository's WebBrowserInterop.cs, references
framework assemblies and embeds the SHDocVw COM interop types. The repository's
retained BSD-3-Clause LICENSE applies to its code; no separate Interop license
was found. No source-to-binary rebuild was performed in this audit.

### Python.NET And Other Wheel Native Components

pythonnet/runtime/Python.Runtime.dll is version 3.0.5.0, SHA-256
`d204ad74dc18cd07320c8e665bd32ec6549b555ce97e61e4d3cf88437a64988e`.
It exactly matches the official 3.0.5 PyPI wheel (archive SHA-256
`f6702d694d5d5b163c9f3f5cc34e0bed8d6857150237fae411fefb883a656d20`)
as well as installed RECORD and the candidate TOC source. Its project license
is MIT, as both installed METADATA and the retained exact-release text state;
no GPL label is inferred from historical versions or the parent project's GPL.

The [v3.0.5 runtime csproj](https://github.com/pythonnet/pythonnet/blob/v3.0.5/src/runtime/Python.Runtime.csproj)
and installed Python.Runtime.deps.json identify
Lost.Compat.NullabilityAttributes 0.0.4. Its NuGet contentFiles are compiled
into the assembly. Read-only PE metadata inspection confirms the corresponding
System.Diagnostics.CodeAnalysis attribute types, including MemberNotNull and
MemberNotNullWhen. The component's original Victor Nova MIT
[LICENSE](packaging/licenses/lost-compat-nullabilityattributes-0.0.4/LICENSE)
is retained. CLR metadata references netstandard, System.Reflection.Emit and
System.Reflection.Emit.ILGeneration; separate DLLs with those names are not in
the candidate. No compiler/analyzer/SourceLink tool DLL is counted as shipped
just because it appears in the deps.json.

Both clr_loader/ffi/dlls/{amd64,x86}/ClrLoader.dll files are shipped, match the
0.2.10 installed wheel RECORD and TOC sources, and use the retained clr-loader
MIT license. No standalone .NET runtime is included.

NumPy/OpenBLAS, pandas (including its two identical wheel-carried MSVCP copies
across numpy.libs and pandas.libs), MarkupSafe, cffi, pydantic-core and the six
Pillow PYD files all match their installed wheel RECORD. NumPy's full supplied
binary/per-component notices and Pillow's 78,014-byte combined notice remain
intact. pandas' installed LICENSE alone omits the upstream LICENSES directory;
all 13 originals from its exact v3.0.2 tag are now retained, including klib,
UltraJSON, NumPy datetime, musl and other incorporated-code notices. Inclusion
of these notices is conservative, not a claim that every upstream tool is shipped.

cffi's x64 source build embeds its bundled libffi_x86_x64 code rather than the
separate conda libffi DLL. Its original Red Hat/Cygnus/Ranjit Mathew/Bo Thorsen/
Roger Sayle notices are retained as exact leading-comment extracts under
[libffi-x86-x64](packaging/licenses/cffi-2.0.0/libffi-x86-x64/).
These are distinct from the newer conda libffi 3.5.2 notice below. The source
build configuration was inspected; a reproducible wheel rebuild was not done.

### Interpreter-Linked Native Libraries

The following collected files were mapped to installed conda file ownership,
not classified just by filenames. Copies in the interpreter root and
Library/bin are traced through the actual TOC paths.

| Candidate file(s) | Installed package | Retained original |
| --- | --- | --- |
| libbz2.dll | bzip2 1.0.8 h0ad9c76_8 | [bzip2 LICENSE](packaging/licenses/bzip2-1.0.8-h0ad9c76_8/LICENSE) |
| ffi-8.dll | libffi 3.5.2 h52bdfb6_0 | [MIT LICENSE](packaging/licenses/libffi-3.5.2-h52bdfb6_0/LICENSE) |
| liblzma.dll | liblzma 5.8.1 h2466b09_2 | [COPYING](packaging/licenses/liblzma-5.8.1-h2466b09_2/COPYING), [0BSD](packaging/licenses/liblzma-5.8.1-h2466b09_2/COPYING.0BSD) |
| libexpat.dll | libexpat 2.7.1 hac47afa_0 | [exact R_2_7_1 MIT COPYING](packaging/licenses/libexpat-2.7.1/COPYING) |
| sqlite3.dll | libsqlite 3.50.4 hf5d6505_0 | [exact-version public-domain statement/blessing](packaging/licenses/libsqlite-3.50.4/LICENSE.md) |
| zlib.dll | libzlib 1.3.1 h2466b09_2 | [Zlib LICENSE](packaging/licenses/libzlib-1.3.1-h2466b09_2/LICENSE) |
| ucrtbase.dll and 43 api-ms-win-*.dll files | ucrt 10.0.26100.0 h57928b3_0; file versions 10.0.26100.4654 | [original Windows SDK terms](packaging/licenses/ucrt-10.0.26100.0-h57928b3_0/LICENSE.txt) |
| VCRUNTIME140.dll and VCRUNTIME140_1.dll | vc14_runtime 14.44.35208 h818238b_32 | [authoritative original LICENSE.RTF](packaging/licenses/vc14_runtime-14.44.35208-h818238b_32/LICENSE.RTF), [package's expressly non-authoritative text conversion](packaging/licenses/vc14_runtime-14.44.35208-h818238b_32/LICENSE.TXT) |

Conda's ucrt recipe records the Microsoft Windows SDK ISO source; its
vc14_runtime recipe records Microsoft's exact vc_redist.x64.exe download and
SHA-256. Their installed package notices were retained, not replaced with
pywebview BSD or CPython PSF texts. This evidence does not itself establish the
release owner's separate right to redistribute Visual C++ runtime files.
No separate libgcc_s_seh-1.dll, libquadmath-0.dll, libwinpthread-1.dll,
concrt140.dll or MSVC installer is collected. NumPy's embedded GCC runtime
terms still apply as documented in its combined notice.

## Specific Unresolved Evidence

This candidate is for local desktop acceptance, not a public-release
clearance. The concrete remaining evidence gaps are:

* proxy-tools: the installed/upstream MIT metadata versus BSD source/LICENSE
  conflict described above has no obtained upstream correction.
* pydantic-core: the installed wheel supplies its own MIT license but not a
  complete native dependency notice/SBOM. The official v2.41.5 Cargo.toml lists
  dependencies including PyO3, regex, serde/serde_json, jiter, speedate, url/idna,
  ahash and others. Their exact compiled/transitive inventory and originals have
  not been reconciled to this wheel. They are not declared MIT by association.
* Microsoft runtime: the two wheel-carried hashed MSVCP DLLs are byte-identical,
  version 14.40.33810.0; their exact original Microsoft package/license provenance
  has not been verified. The retained 14.44 conda runtime notice is not relabeled
  as a verified 14.40 notice. The release owner's redistribution entitlement,
  applicable REDIST-file list and end-user/distributor terms for shipped VC/UCRT
  files have not been verified. Microsoft's [VC redistribution documentation](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)
  and [UCRT deployment documentation](https://learn.microsoft.com/en-us/cpp/windows/universal-crt-deployment?view=msvc-170)
  are the official references; locating a DLL in conda or a wheel is not the grant.
These are evidence gaps, not an assertion of incompatibility, infringement or a
legal determination. Whole-repository provenance, source-offer obligations,
commercial Inno tool entitlement and Native installation/execution acceptance
are outside this file-copy/build audit.

## External Runtime And Platform-Only Dependencies

Microsoft Edge WebView2 Evergreen Runtime itself is not bundled or downloaded
automatically. If missing, the installer offers the
[official Microsoft download page](https://developer.microsoft.com/microsoft-edge/webview2/).
The runtime is supplied separately under Microsoft's terms. This statement does
not exclude the SDK/loader DLLs already present inside pywebview from the native
review above.

The universal lock also contains macholib 1.16.4, qtpy 2.4.3 and PyObjC 12.1
packages (core; Cocoa, Quartz, Security, UniformTypeIdentifiers and WebKit).
They are platform-conditional dependencies and are not installed in the audited
Windows environment. Their notices have not been copied and they must be
audited if a later candidate or a different-platform distribution includes them.

## Independent Project Code

No AGPL project's implementation is copied into this packaging work.
Learning a packaging mechanism does not copy or relicense another project's
implementation. This statement is scoped to this work and is not a substitute
for the release owner's whole-repository provenance review.
