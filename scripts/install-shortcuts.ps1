$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonwPath = Join-Path $projectPath '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonwPath)) { throw 'Run setup.bat first.' }

$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutShell = New-Object -ComObject WScript.Shell
# Unicode escapes keep this script readable by Windows PowerShell 5.1 without a BOM.
$shopName = -join (0x91D1,0x94F2,0x94F2,0x5546,0x5E97,0x52A9,0x624B | ForEach-Object { [char]$_ })
$lineupName = -join (0x91D1,0x94F2,0x94F2,0x9635,0x5BB9,0x914D,0x7F6E,0x5DE5,0x5177 | ForEach-Object { [char]$_ })
$shopFile = -join (0x5546,0x5E97,0x52A9,0x624B | ForEach-Object { [char]$_ })
$lineupFile = -join (0x9635,0x5BB9,0x914D,0x7F6E,0x5DE5,0x5177 | ForEach-Object { [char]$_ })
foreach ($entry in @(@{Name=$shopName; File=$shopFile}, @{Name=$lineupName; File=$lineupFile})) {
    $shortcut = $shortcutShell.CreateShortcut((Join-Path $desktopPath ($entry.Name + '.lnk')))
    $shortcut.TargetPath = $pythonwPath
    $shortcut.Arguments = '"' + (Join-Path $projectPath ($entry.File + '.pyw')) + '"'
    $shortcut.WorkingDirectory = $projectPath
    $shortcut.IconLocation = (Join-Path $projectPath 'assets\jcc_official.ico') + ',0'
    $shortcut.Description = 'JCCAutoD'
    $shortcut.Save()
}
Write-Host 'Created two JCCAutoD desktop shortcuts.'
