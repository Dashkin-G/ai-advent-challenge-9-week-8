# Одна генерация боевой задачи: Claude Code в чистой копии проекта с выбранными правилами → diff, проверки, итог.
# Запуск из корня проекта:
#   .\experiment\generate.ps1 qwen-v1 -Rules v1     правила из experiment\rules\v1, модель Qwen (DashScope)
#   .\experiment\generate.ps1 qwen-v2               текущие правила проекта (CLAUDE.md и .claude в корне)
#   .\experiment\generate.ps1 opus-v2 -Provider claude   модель из настроек claude, по подписке
# Репозиторий не меняется: Claude работает в копии в %TEMP%\claude-rules\<имя>, итог — в experiment\<имя>\.
param(
    [Parameter(Mandatory)][string]$Name,
    [string]$Rules,
    [ValidateSet("alibaba", "claude")][string]$Provider = "alibaba",
    [string]$Model
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $PSScriptRoot $Name
$rulesDir = if ($Rules) { Join-Path $PSScriptRoot "rules\$Rules" } else { $root }
# копия вне проекта: иначе Claude подхватил бы ещё и CLAUDE.md из папок выше
$work = Join-Path $env:TEMP "claude-rules\$Name"
if ((Test-Path $out) -or (Test-Path $work)) { throw "experiment\$Name или $work уже есть — выберите другое имя" }
if (-not (Test-Path "$rulesDir\CLAUDE.md")) { throw "Нет правил $rulesDir\CLAUDE.md" }

# Qwen через Anthropic-совместимый адрес DashScope; переменные — только на время прогона
$vars = @{}
if ($Provider -eq "alibaba") {
    if (-not $Model) { $Model = "qwen3.5-plus-2026-02-15" }
    $key = $env:DASHSCOPE_API_KEY
    foreach ($file in "$root\.env", "$root\..\ai-advent-challenge-9-week-7\.env") {
        if (-not $key -and (Test-Path $file)) {
            $line = Select-String -Path $file -Pattern '^DASHSCOPE_API_KEY=' | Select-Object -First 1
            if ($line) { $key = $line.Line.Split("=", 2)[1].Trim('"', "'", " ") }
        }
    }
    if (-not $key) { throw "Нет ключа DASHSCOPE_API_KEY — задайте переменную или положите .env в корень" }
    $vars = @{
        ANTHROPIC_BASE_URL                       = "https://ws-q1vxaj37wm4fa9q8.ap-southeast-1.maas.aliyuncs.com/apps/anthropic"
        ANTHROPIC_AUTH_TOKEN                     = $key
        ANTHROPIC_MODEL                          = $Model
        ANTHROPIC_DEFAULT_OPUS_MODEL             = $Model
        ANTHROPIC_DEFAULT_SONNET_MODEL           = $Model
        ANTHROPIC_DEFAULT_HAIKU_MODEL            = $Model  # фоновые задачи — тоже Qwen, не подписка
        CLAUDE_CODE_SUBAGENT_MODEL               = $Model  # и субагенты
        CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
    }
}
$vars["PROJECT_DIR"] = (Resolve-Path (Join-Path $root "..\ml-student-dropout")).Path  # копия не рядом с ML-проектом

New-Item -ItemType Directory $out, $work | Out-Null
foreach ($item in "app", "static", "support", "requirements.txt", "ruff.toml", ".gitignore") {
    Copy-Item (Join-Path $root $item) $work -Recurse
}
Copy-Item "$rulesDir\CLAUDE.md", "$rulesDir\.claude" $work -Recurse
Copy-Item "$rulesDir\CLAUDE.md", "$rulesDir\.claude" $out -Recurse  # с какими правилами шла генерация
Get-ChildItem $work -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
New-Item -ItemType Junction (Join-Path $work ".venv") -Target (Join-Path $root ".venv") | Out-Null  # команды проверки из CLAUDE.md
Add-Content "$work\.gitignore" ".venv"  # «.venv/» не ловит ссылку-junction
git -C $work init -q
git -C $work config core.autocrlf false  # копия — только ради diff, концы строк не трогаем
git -C $work add -A
git -C $work -c user.name=baseline -c user.email=baseline@example.com commit -q -m baseline

$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$params = @("-p", "--permission-mode", "acceptEdits", "--output-format", "stream-json", "--verbose")
# permissions из .claude/settings.json в незнакомой папке не действуют — те же разрешения флагом
$params += @("--allowedTools") + ((Get-Content "$rulesDir\.claude\settings.json" -Raw | ConvertFrom-Json).permissions.allow)
if ($Model) { $params += @("--model", $Model) }
$saved = @{}
foreach ($k in $vars.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); Set-Item "env:$k" $vars[$k] }
$started = Get-Date
Push-Location $work
try {
    Get-Content "$PSScriptRoot\prompt.md" -Raw -Encoding utf8 | claude @params | Set-Content "$out\log.jsonl" -Encoding utf8
} finally {
    Pop-Location
    foreach ($k in $vars.Keys) { if ($null -eq $saved[$k]) { Remove-Item "env:$k" -ErrorAction SilentlyContinue } else { Set-Item "env:$k" $saved[$k] } }
}
$seconds = [math]::Round(((Get-Date) - $started).TotalSeconds)

# Итог: модель и чей ключ, ответ, ходы, токены, какие инструменты, субагенты и скиллы звал Claude
$events = Get-Content "$out\log.jsonl" -Encoding utf8 | ForEach-Object { $_ | ConvertFrom-Json }
$result = $events | Where-Object type -eq "result" | Select-Object -Last 1
$init = $events | Where-Object { $_.type -eq "system" -and $_.subtype -eq "init" } | Select-Object -First 1
$tools = $events | Where-Object type -eq "assistant" | ForEach-Object { $_.message.content } | Where-Object type -eq "tool_use"
$named = $tools | ForEach-Object { if ($_.name -in "Task", "Agent") { "Agent:$($_.input.subagent_type)" } elseif ($_.name -eq "Skill") { "Skill:$($_.input.skill)" } else { $_.name } }
$denied = ($events | Where-Object type -eq "user" | ForEach-Object { $_.message.content } | Where-Object { $_.is_error }).Count
$usage = $result.usage
@(
    "# Генерация $Name — $($init.model) ($Provider), правила: $(if ($Rules) { $Rules } else { 'текущие' }), $($started.ToString('dd.MM.yyyy HH:mm'))",
    "",
    "Время: $seconds с · ходов: $($result.num_turns) · ошибок инструментов: $denied · " +
    "токенов: вход $($usage.input_tokens + $usage.cache_read_input_tokens + $usage.cache_creation_input_tokens), выход $($usage.output_tokens)",
    "Инструменты: $(($named | Group-Object | ForEach-Object { "$($_.Name) ×$($_.Count)" }) -join ', ')",
    "",
    "## Ответ Claude Code",
    "",
    $result.result
) | Set-Content "$out\result.md" -Encoding utf8

git -C $work add -A
git -C $work diff --cached | Set-Content "$out\changes.diff" -Encoding utf8
Push-Location $work
try {
    & .venv\Scripts\ruff.exe check app 2>&1 | Set-Content "$out\checks.txt" -Encoding utf8
    "--- import app.main" | Add-Content "$out\checks.txt" -Encoding utf8
    & .venv\Scripts\python.exe -c "import app.main; print('ok')" 2>&1 | Add-Content "$out\checks.txt" -Encoding utf8
    "--- GET /api/search без Ollama (experiment\smoke.py)" | Add-Content "$out\checks.txt" -Encoding utf8
    $env:PROJECT_DIR = $vars["PROJECT_DIR"]
    $env:PYTHONUTF8 = "1"
    & .venv\Scripts\python.exe "$PSScriptRoot\smoke.py" 2>$null | Add-Content "$out\checks.txt" -Encoding utf8
} finally { Pop-Location; Remove-Item env:PROJECT_DIR, env:PYTHONUTF8 -ErrorAction SilentlyContinue }
Write-Host "Готово за $seconds с: experiment\$Name\ — result.md, changes.diff, checks.txt; копия проекта — $work"
