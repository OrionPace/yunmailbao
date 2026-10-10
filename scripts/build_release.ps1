[CmdletBinding()]
param([switch]$PackageOnly)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RepoRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$BuildRoot = Join-Path $RepoRoot '.build'
$CandidateRoot = Join-Path $BuildRoot 'candidate'
$CandidateDir = Join-Path $CandidateRoot 'YunYouBao'
$WorkDir = Join-Path $BuildRoot 'work'
$ReleaseRoot = Join-Path $RepoRoot 'release'
$ProvenancePath = Join-Path $CandidateRoot 'build-provenance.json'
$Iscc = Join-Path $RepoRoot '.tools\InnoSetup\ISCC.exe'
$python = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$ProductName = -join @([char]0x4E91, [char]0x90AE, [char]0x5B9D)
$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Sha256 {
    param([string]$Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = $null
    try {
        $stream = [IO.File]::OpenRead($Path)
        return [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        if ($stream) { $stream.Dispose() }
        $algorithm.Dispose()
    }
}

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed (exit $LASTEXITCODE)." }
}

function Get-ToolVersion {
    param([string]$Command, [string[]]$Arguments)
    $result = & $Command @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Cannot read version: $Command" }
    return ($result | Out-String).Trim()
}

function Write-Json {
    param([string]$Path, $Value)
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 10), $Utf8)
}

function Assert-NoLinks {
    param([string]$Path)
    if ((Test-Path -LiteralPath $Path) -and ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing a linked build path: $Path"
    }
}

function Reset-BuildDirectory {
    param([string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ($fullPath -notin @($CandidateRoot, $WorkDir)) {
        throw "Refusing to remove a non-build directory: $fullPath"
    }
    Assert-NoLinks $fullPath
    if (Test-Path -LiteralPath $fullPath) {
        if (Get-ChildItem -LiteralPath $fullPath -Force -Recurse | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
            throw "Refusing to remove a build directory containing links: $fullPath"
        }
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
    New-Item -ItemType Directory -Path $fullPath | Out-Null
}

function Get-CandidateInventory {
    Assert-NoLinks $BuildRoot
    Assert-NoLinks $CandidateRoot
    Assert-NoLinks $CandidateDir
    if (-not (Test-Path -LiteralPath (Join-Path $CandidateDir 'YunYouBao.exe') -PathType Leaf)) {
        throw 'No candidate executable. Run a normal build after source work is complete.'
    }
    $allItems = @(Get-ChildItem -LiteralPath $CandidateDir -Recurse -Force)
    if ($allItems | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) {
        throw 'Candidate must not contain links.'
    }
    foreach ($item in $allItems) {
        if ($item.Name -like '.env*') { throw 'Environment files are forbidden in the candidate.' }
    }
    foreach ($base in @($CandidateDir, (Join-Path $CandidateDir '_internal'))) {
        foreach ($name in @('runtime', 'logs', 'state', 'uploads', 'data')) {
            if (Test-Path -LiteralPath (Join-Path $base $name)) { throw "Personal runtime directory is forbidden: $name" }
        }
    }
    foreach ($asset in @('LICENSE', 'THIRD_PARTY_NOTICES.md', 'static\script.js', 'assets\branding\yunyoubao-fox-v1.ico')) {
        if (-not (Test-Path -LiteralPath (Join-Path $CandidateDir "_internal\$asset") -PathType Leaf)) {
            throw "Required candidate asset missing: $asset"
        }
    }
    return @($allItems | Where-Object { -not $_.PSIsContainer } | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($CandidateDir.Length + 1).Replace('\', '/')
            size = $_.Length
            sha256 = Get-Sha256 $_.FullName
        }
    })
}

function Archive-ReleaseFiles {
    param([string]$SourceDir)
    if ($SourceDir -notin @($ReleaseRoot, $ReleaseDir)) {
        throw "Refusing to archive a non-release directory: $SourceDir"
    }
    Assert-NoLinks $SourceDir
    $files = @(Get-ChildItem -LiteralPath $SourceDir -File -Force)
    if ($files.Count -eq 0) { return }
    foreach ($file in $files) { Assert-NoLinks $file.FullName }
    $archiveRoot = Join-Path $ReleaseDir 'archive'
    Assert-NoLinks $archiveRoot
    New-Item -ItemType Directory -Path $archiveRoot -Force | Out-Null
    $archiveDir = Join-Path $archiveRoot (Get-Date -Format 'yyyyMMdd-HHmmss-fffffff')
    # No -Force: a timestamp collision must fail without replacing an archive.
    New-Item -ItemType Directory -Path $archiveDir | Out-Null
    foreach ($file in $files) {
        $target = Join-Path $archiveDir $file.Name
        [IO.File]::Move($file.FullName, $target)
    }
    Write-Host "Previous release files archived: $archiveDir"
}

Push-Location $RepoRoot
try {
    Assert-NoLinks $BuildRoot
    Assert-NoLinks (Join-Path $RepoRoot '.tools')
    Assert-NoLinks (Join-Path $RepoRoot '.tools\InnoSetup')
    if (-not (Test-Path -LiteralPath $Iscc -PathType Leaf)) {
        throw 'Install official Inno Setup 7.1.0 x64 in .tools\InnoSetup first.'
    }
    $innoVersion = Get-ToolVersion $Iscc @('--version')
    if ($innoVersion -notmatch '(^|\D)7\.1\.0($|\D)') { throw "Inno Setup 7.1.0 required: $innoVersion" }
    if (-not $PackageOnly) {
        Invoke-Checked 'uv' @('sync', '--locked', '--python', '3.12')
    }
    $AppVersion = Get-ToolVersion $python @('-B', '-c', "import pathlib, tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])")
    if ($AppVersion -notmatch '^\d+\.\d+\.\d+$') { throw "Installer requires a numeric major.minor.patch version: $AppVersion" }
    $ReleaseDir = Join-Path $ReleaseRoot $AppVersion
    $InstallerName = "$ProductName-$AppVersion-setup.exe"
    if (-not $PackageOnly) {
        Invoke-Checked $python @('-c', "import struct, sys; assert sys.version_info[:2] == (3, 12) and struct.calcsize('P') == 8, 'Python 3.12 x64 required'")
        $commit = Get-ToolVersion 'git' @('rev-parse', 'HEAD')
        $status = & git status --porcelain --untracked-files=normal
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect source worktree.' }
        $source = [ordered]@{ commit = $commit; dirty = [bool]($status); captured_at_utc = [DateTime]::UtcNow.ToString('o') }
        $buildTools = [ordered]@{
            python = Get-ToolVersion $python @('--version')
            uv = Get-ToolVersion 'uv' @('--version')
            pyinstaller = Get-ToolVersion $python @('-c', 'import PyInstaller; print(PyInstaller.__version__)')
            git = Get-ToolVersion 'git' @('--version')
        }
        Reset-BuildDirectory $CandidateRoot
        Reset-BuildDirectory $WorkDir
        Invoke-Checked $python @('-m', 'PyInstaller', '--noconfirm', '--clean', '--distpath', $CandidateRoot, '--workpath', $WorkDir, 'auto_email.spec')
        $provenance = [ordered]@{
            schema_version = 1
            app_version = $AppVersion
            source = $source
            tools = $buildTools
            files = @(Get-CandidateInventory)
        }
        Write-Json $ProvenancePath $provenance
    }

    Assert-NoLinks $CandidateRoot
    if (-not (Test-Path -LiteralPath $ProvenancePath -PathType Leaf)) {
        throw 'Candidate provenance missing in .build\candidate. PackageOnly never uses legacy dist directories.'
    }
    $provenance = Get-Content -LiteralPath $ProvenancePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($provenance.schema_version -ne 1 -or $provenance.app_version -ne $AppVersion) {
        throw 'Candidate provenance schema or version mismatch.'
    }
    $inventory = @(Get-CandidateInventory)
    $recorded = @($provenance.files)
    if ($inventory.Count -ne $recorded.Count) { throw 'Candidate file count changed since build.' }
    for ($i = 0; $i -lt $inventory.Count; $i++) {
        if ($inventory[$i].path -ne $recorded[$i].path -or $inventory[$i].sha256 -ne $recorded[$i].sha256 -or $inventory[$i].size -ne $recorded[$i].size) {
            throw 'Candidate content changed since build. Rebuild before packaging.'
        }
    }
    Assert-NoLinks $ReleaseRoot
    Assert-NoLinks $ReleaseDir
    New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
    # Preserve legacy root outputs and previous builds of this version before packaging.
    Archive-ReleaseFiles $ReleaseRoot
    Archive-ReleaseFiles $ReleaseDir
    Invoke-Checked $Iscc @('--no-ide-signtools', '--no-signing', "--define=CandidateDir=$CandidateDir", "--define=ReleaseDir=$ReleaseDir", "--define=AppVersion=$AppVersion", (Join-Path $RepoRoot 'packaging\yunyoubao.iss'))
    $installer = Join-Path $ReleaseDir $InstallerName
    $hash = Get-Sha256 $installer
    $manifest = [ordered]@{
        schema_version = 1
        product = 'YunYouBao'
        app_version = $AppVersion
        packaged_at_utc = [DateTime]::UtcNow.ToString('o')
        source = $provenance.source
        build_tools = $provenance.tools
        packaging_tools = [ordered]@{ inno_setup = $innoVersion; powershell = $PSVersionTable.PSVersion.ToString() }
        package_only = [bool]$PackageOnly
        signed = $false
        installer = [ordered]@{ filename = $InstallerName; sha256 = $hash; size = (Get-Item -LiteralPath $installer).Length }
        candidate_files = $inventory
    }
    Write-Json (Join-Path $ReleaseDir 'build-manifest.json') $manifest
    $manifestHash = Get-Sha256 (Join-Path $ReleaseDir 'build-manifest.json')
    [IO.File]::WriteAllText((Join-Path $ReleaseDir 'SHA256SUMS.txt'), "$hash  $InstallerName`n$manifestHash  build-manifest.json`n", $Utf8)
    Write-Host "Release ready (unsigned): $installer"
}
finally {
    Pop-Location
}
