#Requires -Version 5.1
<#
    Установка русской локализации Ace Attorney Investigations 2 (дело 2).

    Кладётся рядом с папкой data\ и файлом files.json — их собирает
    tools/make_installer.py. Ничего, кроме Windows и PowerShell, не требует.

        install.bat                   обычная установка
        install.ps1 -Check            только показать, что будет сделано
        install.ps1 -Uninstall        вернуть оригиналы из бэкапа
        install.ps1 -GamePath "D:\..." если игру не удалось найти самому
#>
[CmdletBinding()]
param(
    [string]$GamePath,
    [switch]$Check,
    [switch]$Uninstall,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$OutputEncoding = [System.Text.Encoding]::UTF8
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackupDirName = '_backup_ru'

function Say([string]$text, [string]$color = 'Gray') { Write-Host $text -ForegroundColor $color }

function Done([int]$code) {
    # окно открыто двойным кликом — без паузы оно закроется раньше, чем прочитают.
    # при запуске из консоли Read-Host недоступен, и это не повод падать
    Say ''
    Say 'Нажмите Enter, чтобы закрыть окно.'
    try { [void](Read-Host) } catch { }
    exit $code
}

function Fail([string]$text) {
    Say ''
    Say "ОШИБКА: $text" 'Red'
    Done 1
}

# --- где стоит игра -----------------------------------------------------------

function Get-SteamRoots {
    $roots = New-Object System.Collections.Generic.List[string]
    foreach ($key in @(
        @{ Path = 'HKCU:\Software\Valve\Steam';                  Name = 'SteamPath' },
        @{ Path = 'HKLM:\SOFTWARE\WOW6432Node\Valve\Steam';      Name = 'InstallPath' },
        @{ Path = 'HKLM:\SOFTWARE\Valve\Steam';                  Name = 'InstallPath' }
    )) {
        try {
            $value = (Get-ItemProperty -Path $key.Path -Name $key.Name -ErrorAction Stop).($key.Name)
            if ($value) { $roots.Add(($value -replace '/', '\')) }
        } catch { }
    }
    foreach ($guess in @("${env:ProgramFiles(x86)}\Steam", "$env:ProgramFiles\Steam")) {
        if (Test-Path $guess) { $roots.Add($guess) }
    }
    return $roots | Select-Object -Unique
}

function Get-SteamLibraries {
    # Библиотеки Steam живут не только на системном диске: пути перечислены
    # в libraryfolders.vdf строками вида   "path"   "D:\\SteamLibrary"
    $libs = New-Object System.Collections.Generic.List[string]
    foreach ($root in (Get-SteamRoots)) {
        $libs.Add($root)
        foreach ($vdf in @("$root\steamapps\libraryfolders.vdf", "$root\config\libraryfolders.vdf")) {
            if (-not (Test-Path $vdf)) { continue }
            $text = Get-Content -LiteralPath $vdf -Raw
            foreach ($m in [regex]::Matches($text, '"path"\s*"([^"]+)"')) {
                $libs.Add(($m.Groups[1].Value -replace '\\\\', '\'))
            }
        }
    }
    return $libs | Select-Object -Unique
}

function Find-Game([string]$marker) {
    if ($GamePath) {
        if (Test-Path (Join-Path $GamePath $marker)) { return (Resolve-Path $GamePath).Path }
        Fail "в папке `"$GamePath`" нет $marker — это не папка игры."
    }
    foreach ($lib in (Get-SteamLibraries)) {
        $candidate = Join-Path $lib 'steamapps\common\Ace Attorney Investigations Collection'
        if (Test-Path (Join-Path $candidate $marker)) { return (Resolve-Path $candidate).Path }
    }
    return $null
}

# --- проверки перед записью ---------------------------------------------------

function Assert-GameClosed {
    if (Get-Process -Name 'GK12' -ErrorAction SilentlyContinue) {
        Fail 'игра запущена. Закройте её — при работающей игре файлы заблокированы.'
    }
}

function Test-Writable([string]$dir) {
    # прав нет, если не удалась сама запись; убрать пробник — дело десятое,
    # и его провал (скажем, на пути с коротким именем вида 75BD~1) правами не считаем
    $probe = Join-Path $dir ([System.IO.Path]::GetRandomFileName())
    try { [System.IO.File]::WriteAllText($probe, 'x') } catch { return $false }
    try { [System.IO.File]::Delete($probe) } catch { }
    return $true
}

function Copy-File([string]$from, [string]$to) {
    # .NET, а не Copy-Item: тот спотыкается о пути с квадратными скобками и 8.3-именами
    [System.IO.File]::Copy($from, $to, $true)
}

function Get-Sha([string]$path) { return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() }

# --- разбор задания -----------------------------------------------------------

$manifestPath = Join-Path $Root 'files.json'
if (-not (Test-Path $manifestPath)) { Fail "рядом со скриптом нет files.json — комплект неполный." }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

Say ''
Say '  Русская локализация Ace Attorney Investigations 2' 'Cyan'
Say '  ------------------------------------------------' 'Cyan'
Say ''

$game = Find-Game $manifest.marker
if (-not $game) {
    Fail @"
не удалось найти игру.

Проверено: реестр Steam и все библиотеки из libraryfolders.vdf.
Если игра стоит где-то ещё, укажите папку вручную — ту, в которой лежит GK12.exe:

  powershell -ExecutionPolicy Bypass -File install.ps1 -GamePath "D:\Games\Ace Attorney Investigations Collection"
"@
}
Say "  Игра найдена: $game"

$backupRoot = Join-Path $game $BackupDirName

# --- откат --------------------------------------------------------------------

if ($Uninstall) {
    Assert-GameClosed
    if (-not (Test-Path $backupRoot)) {
        Fail @"
бэкапа нет — восстанавливать нечем.

Оригиналы можно вернуть самой Steam: свойства игры -> Установленные файлы ->
Проверить целостность файлов игры.
"@
    }
    $back = 0
    foreach ($f in $manifest.files) {
        $saved = Join-Path $backupRoot $f.path
        $target = Join-Path $game $f.path
        if (-not (Test-Path $saved)) { Say "  - нет в бэкапе: $($f.path)" 'DarkYellow'; continue }
        if ((Get-Sha $saved) -ne $f.sha_original) { Say "  X бэкап испорчен: $($f.path)" 'Red'; continue }
        if ((Test-Path $target) -and (Get-Sha $target) -eq $f.sha_original) { continue }
        Copy-File $saved $target
        $back++
        Say "  < возвращён $($f.path)"
    }
    Say ''
    Say "  Восстановлено файлов: $back" 'Green'
    Say "  Бэкап оставлен на месте: $backupRoot"
    Done 0
}

# --- план установки -----------------------------------------------------------

$plan = New-Object System.Collections.Generic.List[object]
$installed = 0
$foreign = New-Object System.Collections.Generic.List[string]
$missing = New-Object System.Collections.Generic.List[string]

foreach ($f in $manifest.files) {
    $target = Join-Path $game $f.path
    $source = Join-Path $Root (Join-Path 'data' $f.path)
    if (-not (Test-Path $source)) { Fail "в комплекте нет файла data\$($f.path)" }
    if (-not (Test-Path $target)) { $missing.Add($f.path); continue }

    $hash = Get-Sha $target
    if ($hash -eq $f.sha_translated) { $installed++; continue }
    if ($hash -ne $f.sha_original) { $foreign.Add($f.path); if (-not $Force) { continue } }
    $plan.Add([pscustomobject]@{ File = $f; Target = $target; Source = $source; WasOriginal = ($hash -eq $f.sha_original) })
}

if ($missing.Count -gt 0) {
    Fail @"
версия игры не та, на которой собирался перевод.

Не найдено файлов: $($missing.Count), например
  $($missing[0])

Имена бандлов содержат хеш сборки, и после обновления игры они меняются.
Перевод придётся пересобрать на новой версии.
"@
}

if ($foreign.Count -gt 0 -and -not $Force) {
    Fail @"
$($foreign.Count) файл(ов) игры уже кем-то изменены — ни оригинал, ни наш перевод:
  $($foreign[0])

Скорее всего, стоит другой мод или другая версия перевода. Сначала верните
оригиналы (Steam -> Проверить целостность файлов игры), потом ставьте заново.
Если вы точно знаете, что делаете: install.ps1 -Force
"@
}

Say "  Уже установлено: $installed из $($manifest.files.Count)"
Say "  К установке:     $($plan.Count)"

if ($plan.Count -eq 0) {
    Say ''
    Say '  Перевод уже стоит целиком, делать нечего.' 'Green'
    Done 0
}

$bytes = 0
foreach ($p in $plan) { $bytes += [int64]$p.File.size }   # PS 5.1: Measure-Object не берёт scriptblock
Say ("  Объём:           {0:N0} МБ" -f ($bytes / 1MB))

if ($Check) {
    Say ''
    foreach ($p in $plan) { Say "  -> $($p.File.path)" }
    Say ''
    Say '  Это была проверка, ничего не изменено.' 'Yellow'
    Done 0
}

# --- запись -------------------------------------------------------------------

Assert-GameClosed

if (-not (Test-Writable $game)) {
    Fail @"
нет прав на запись в папку игры.

Игра стоит в защищённой папке (обычно Program Files). Щёлкните по install.bat
правой кнопкой -> «Запуск от имени администратора».
"@
}

$drive = (Get-Item $game).PSDrive
if ($drive -and $null -ne $drive.Free -and $drive.Free -lt ($bytes * 2)) {
    Fail ("на диске {0}: мало места. Нужно примерно {1:N0} МБ (файлы плюс бэкап), свободно {2:N0} МБ." -f `
        $drive.Name, ($bytes * 2 / 1MB), ($drive.Free / 1MB))
}

Say ''
Say '  Ставлю. Оригиналы сохраняются в папку _backup_ru внутри игры.' 'Yellow'
Say ''

$done = 0
foreach ($p in $plan) {
    $rel = $p.File.path
    # бэкапим только настоящий оригинал: иначе поверх него ляжет чужая правка
    if ($p.WasOriginal) {
        $saved = Join-Path $backupRoot $rel
        if (-not (Test-Path $saved)) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $saved) | Out-Null
            Copy-File $p.Target $saved
        }
    }
    Copy-File $p.Source $p.Target
    if ((Get-Sha $p.Target) -ne $p.File.sha_translated) {
        Fail "файл $rel скопировался неправильно — контрольная сумма не сошлась."
    }
    $done++
    Say ("  [{0}/{1}] {2}" -f $done, $plan.Count, $rel) 'Green'
}

Say ''
Say "  Готово: установлено $done файл(ов)." 'Green'
Say ''
Say '  Запустите игру и выберите в настройках язык «Русский»' 'Cyan'
Say '  (он занимает место немецкого).' 'Cyan'
Say ''
Say '  Откат: install.ps1 -Uninstall'
Done 0
