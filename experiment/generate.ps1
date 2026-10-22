# Один прогон Claude Code в копии проекта без человека → diff, проверки, итог.
# Запуск из корня проекта:
#   .\experiment\generate.ps1 qwen-v1 -Rules v1     день 36: правила из experiment\rules\v1, задача experiment\prompt.md
#   .\experiment\generate.ps1 qwen-v2               день 36: текущие правила проекта (CLAUDE.md и .claude в корне)
#   .\experiment\generate.ps1 opus-v2 -Provider claude   модель из настроек claude, по подписке
#   .\experiment\generate.ps1 bug-fix-v1 -Agent bug-fix -Model qwen3.5-122b-a10b
#                       день 37: профиль .claude\agents\bug-fix.md, задача и её проверка — experiment\tasks\bug-fix.*
#   .\experiment\generate.ps1 commit-check-v1 -Agent commit-check -Clone -Model qwen3.5-122b-a10b
#                       -Clone: копия с историей git и незакоммиченными правками проекта — то, что уйдёт в коммит
#   .\experiment\generate.ps1 qa-tests-v1 -Agent qa -Task qa-tests -Clone -Model qwen3.5-122b-a10b
#                       день 38: у профиля несколько задач — -Task выбирает experiment\tasks\<задача>.md; MCP-серверы —
#                       из .mcp.json копии; отчёты QA со скриншотами (reports\) — в experiment\<имя>\reports\
#   .\experiment\generate.ps1 local-4b -Provider ollama -Model qwen3.5:4b -Rules qwen-v2 -Ref e9565b9
#                       день 39: локальная модель через Anthropic-совместимый API Ollama; -Rules <прогон> — правила,
#                       с которыми шёл облачный прогон; -Ref — код из коммита (для bug-fix — с багом, до фикса дня 37);
#                       -Context и -Gpu — контекст и слоёв на видеокарте: вариант модели в Ollama, например qwen3-coder:30b-48k-gpu32
# Репозиторий не меняется: Claude работает в копии в %TEMP%\claude-rules\<имя>, итог — в experiment\<имя>\.
param(
    [Parameter(Mandatory)][string]$Name,
    [string]$Rules,
    [string]$Agent,
    [string]$Task,
    [switch]$Clone,
    [string]$Ref,
    [ValidateSet("alibaba", "claude", "ollama")][string]$Provider = "alibaba",
    [string]$Model,
    [int]$Context = 65536,  # контекст локальной модели: промпт Claude Code ~25 тыс. токенов + файлы и вывод команд
    [int]$Gpu = -1  # слоёв локальной модели на видеокарте; -1 — сколько решит Ollama
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$out = Join-Path $PSScriptRoot $Name
# -Rules: версия из experiment\rules\ или правила, которые сохранил прошлый прогон в experiment\<прогон>\
$rulesDir = if (-not $Rules) { $root } elseif (Test-Path "$PSScriptRoot\rules\$Rules") { "$PSScriptRoot\rules\$Rules" } else { "$PSScriptRoot\$Rules" }
if ($Agent -and -not $Task) { $Task = $Agent }  # задача профиля по умолчанию — tasks\<профиль>.md
$prompt = if ($Task) { Join-Path $PSScriptRoot "tasks\$Task.md" } else { Join-Path $PSScriptRoot "prompt.md" }
$check = if ($Task) { Join-Path $PSScriptRoot "tasks\$Task.py" } else { Join-Path $PSScriptRoot "smoke.py" }  # если есть
# копия вне проекта: иначе Claude подхватил бы ещё и CLAUDE.md из папок выше
$work = Join-Path $env:TEMP "claude-rules\$Name"
if ((Test-Path $out) -or (Test-Path $work)) { throw "experiment\$Name или $work уже есть — выберите другое имя" }
if ($Clone -and ($Rules -or $Ref)) { throw "-Clone берёт проект как есть — без -Rules и -Ref" }
if (-not (Test-Path "$rulesDir\CLAUDE.md")) { throw "Нет правил $rulesDir\CLAUDE.md" }
if ($Agent -and -not (Test-Path "$rulesDir\.claude\agents\$Agent.md")) { throw "Нет профиля $rulesDir\.claude\agents\$Agent.md" }
if (-not (Test-Path $prompt)) { throw "Нет задачи $prompt" }

# Qwen через Anthropic-совместимый адрес DashScope или локальная модель через такой же API Ollama;
# переменные — только на время прогона
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
        ANTHROPIC_BASE_URL   = "https://ws-q1vxaj37wm4fa9q8.ap-southeast-1.maas.aliyuncs.com/apps/anthropic"
        ANTHROPIC_AUTH_TOKEN = $key
    }
} elseif ($Provider -eq "ollama") {
    if (-not $Model) { throw "Укажите модель Ollama: -Model qwen3.5:4b" }
    # контекст Anthropic API не передаёт, а по умолчанию у Ollama 4–32 тыс. — вариант модели со своим num_ctx;
    # num_gpu — когда модель целиком не влезает в общую память встроенной видеокарты и llama-server падает при загрузке
    $variant = "$Model-$($Context / 1024)k"
    $modelfile = "FROM $Model`nPARAMETER num_ctx $Context"
    if ($Gpu -ge 0) { $variant += "-gpu$Gpu"; $modelfile += "`nPARAMETER num_gpu $Gpu" }
    $modelfile | Set-Content "$env:TEMP\$Name.Modelfile" -Encoding ascii  # без BOM
    cmd /c "ollama create $variant -f `"$env:TEMP\$Name.Modelfile`" >nul 2>&1"  # ход работы — в stderr, не ошибка
    if ($LASTEXITCODE) { throw "Нет модели $Model в Ollama — скачайте: ollama pull $Model" }
    Remove-Item "$env:TEMP\$Name.Modelfile"
    $Model = $variant
    $vars = @{
        ANTHROPIC_BASE_URL   = "http://127.0.0.1:11434"
        ANTHROPIC_AUTH_TOKEN = "ollama"  # ключ Ollama не проверяет
        API_TIMEOUT_MS       = "3600000"  # первый ответ локальной модели — минуты: промпт Claude Code ~25 тыс. токенов
        NO_PROXY             = "127.0.0.1,localhost"  # мимо системного прокси
    }
}
if ($Provider -ne "claude") {
    # фоновые задачи и субагенты — та же модель, не подписка
    foreach ($k in "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
                   "ANTHROPIC_DEFAULT_HAIKU_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL") { $vars[$k] = $Model }
    $vars["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
}
$vars["PROJECT_DIR"] = (Resolve-Path (Join-Path $root "..\ml-student-dropout")).Path  # копия не рядом с ML-проектом
$OutputEncoding = [Console]::InputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)

New-Item -ItemType Directory $out | Out-Null
if ($Clone) {
    git clone -q $root $work  # история и текущая ветка — как в проекте
    # незакоммиченное — поверх; игнорируемое (.env, data, CLAUDE.local.md) в копию не попадает
    $changed = @(git -C $root -c core.quotepath=false diff --name-only HEAD) +
               @(git -C $root -c core.quotepath=false ls-files --others --exclude-standard)
    foreach ($file in $changed) {
        $target = Join-Path $work $file
        if (Test-Path (Join-Path $root $file)) {
            New-Item -ItemType Directory (Split-Path $target) -Force | Out-Null
            Copy-Item (Join-Path $root $file) $target
        } else { Remove-Item $target }  # удалён в проекте
    }
} else {
    New-Item -ItemType Directory $work | Out-Null
    $code = "app", "static", "support", "requirements.txt", "ruff.toml", ".gitignore"
    if ($Ref) {
        # код из коммита: задача bug-fix — на версии с багом, до фикса дня 37
        git -C $root archive -o "$work\code.tar" $Ref @code
        tar -xf "$work\code.tar" -C $work
        Remove-Item "$work\code.tar"
    } else {
        foreach ($item in $code) { Copy-Item (Join-Path $root $item) $work -Recurse }
    }
    Copy-Item "$rulesDir\CLAUDE.md", "$rulesDir\.claude" $work -Recurse
    Get-ChildItem $work -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
    git -C $work init -q
    git -C $work config core.autocrlf false  # копия — только ради diff, концы строк не трогаем
}
Copy-Item "$rulesDir\CLAUDE.md", "$rulesDir\.claude" $out -Recurse  # с какими правилами и профилями шёл прогон
Add-Content "$work\.git\info\exclude" ".venv"  # «.venv/» из .gitignore не ловит ссылку-junction
New-Item -ItemType Junction (Join-Path $work ".venv") -Target (Join-Path $root ".venv") | Out-Null  # команды проверки из CLAUDE.md
if (-not $Clone) {
    git -C $work add -A
    git -C $work -c user.name=baseline -c user.email=baseline@example.com commit -q -m baseline
}

# Снимок рабочей папки копии — дерево git через отдельный индекс: индекс копии, который видит Claude, не меняется
function Snapshot {
    $env:GIT_INDEX_FILE = "$work\.git\snapshot-index"
    try { git -C $work add -A | Out-Null; git -C $work write-tree } finally { Remove-Item env:GIT_INDEX_FILE }
}
$before = Snapshot

$params = @("-p", "--permission-mode", "acceptEdits", "--output-format", "stream-json", "--verbose")
if ($Agent) { $params += @("--agent", $Agent) }
# permissions из .claude/settings.json в незнакомой папке не действуют — те же разрешения флагом
$params += @("--allowedTools") + ((Get-Content "$rulesDir\.claude\settings.json" -Raw | ConvertFrom-Json).permissions.allow)
# MCP-серверы проекта (.mcp.json) там же без подтверждения не запускаются — тоже флагом; чужие MCP из глобального конфига не нужны
if (Test-Path "$work\.mcp.json") { $params += @("--mcp-config", "$work\.mcp.json", "--strict-mcp-config") }
if ($Model) { $params += @("--model", $Model) }
$saved = @{}
foreach ($k in $vars.Keys) { $saved[$k] = [Environment]::GetEnvironmentVariable($k); Set-Item "env:$k" $vars[$k] }
$started = Get-Date
Push-Location $work
try {
    Get-Content $prompt -Raw -Encoding utf8 | claude @params | Set-Content "$out\log.jsonl" -Encoding utf8
} finally {
    Pop-Location
    foreach ($k in $vars.Keys) { if ($null -eq $saved[$k]) { Remove-Item "env:$k" -ErrorAction SilentlyContinue } else { Set-Item "env:$k" $saved[$k] } }
}
$seconds = [math]::Round(((Get-Date) - $started).TotalSeconds)
$after = Snapshot
if (Test-Path "$work\reports") { Copy-Item "$work\reports" $out -Recurse }  # отчёты QA со скриншотами

# Итог: модель и чей ключ, ответ, ходы, токены, какие инструменты, субагенты и скиллы звал Claude
$events = Get-Content "$out\log.jsonl" -Encoding utf8 | ForEach-Object { $_ | ConvertFrom-Json }
# первый result — основная работа; следующие — ответы на уведомления о фоновых задачах (сервер для smoke), их ходы и
# токены — тоже в счёт
$results = @($events | Where-Object type -eq "result")
$init = $events | Where-Object { $_.type -eq "system" -and $_.subtype -eq "init" } | Select-Object -First 1
$tools = $events | Where-Object type -eq "assistant" | ForEach-Object { $_.message.content } | Where-Object type -eq "tool_use"
$named = $tools | ForEach-Object { if ($_.name -in "Task", "Agent") { "Agent:$($_.input.subagent_type)" } elseif ($_.name -eq "Skill") { "Skill:$($_.input.skill)" } else { $_.name } }
$denied = ($events | Where-Object type -eq "user" | ForEach-Object { $_.message.content } | Where-Object { $_.is_error }).Count
$tokensIn = ($results | ForEach-Object { $_.usage.input_tokens + $_.usage.cache_read_input_tokens + $_.usage.cache_creation_input_tokens } | Measure-Object -Sum).Sum
$tokensOut = ($results | ForEach-Object { $_.usage.output_tokens } | Measure-Object -Sum).Sum
$what = if ($Agent) { "профиль $Agent$(if ($Task -ne $Agent) { ", задача $Task" })" } else { "правила: $(if ($Rules) { $Rules } else { 'текущие' })" }
if ($Ref) { $what += ", код $Ref" }
@(
    "# Прогон $Name — $($init.model) ($Provider), $what, $($started.ToString('dd.MM.yyyy HH:mm'))",
    "",
    "Время: $seconds с · ходов: $(($results | Measure-Object num_turns -Sum).Sum) · ошибок инструментов: $denied · " +
    "токенов: вход $tokensIn, выход $tokensOut",
    "Инструменты: $(($named | Group-Object | ForEach-Object { "$($_.Name) ×$($_.Count)" }) -join ', ')",
    "",
    "## Ответ Claude Code",
    "",
    $results[0].result
) | Set-Content "$out\result.md" -Encoding utf8

git -C $work diff $before $after | Set-Content "$out\changes.diff" -Encoding utf8
Push-Location $work
try {
    $env:PROJECT_DIR = $vars["PROJECT_DIR"]
    $env:PYTHONUTF8 = "1"
    $lint = @("app") + @(if (Test-Path tests) { "tests" })
    & .venv\Scripts\ruff.exe check @lint 2>&1 | Set-Content "$out\checks.txt" -Encoding utf8
    "--- import app.main" | Add-Content "$out\checks.txt" -Encoding utf8
    & .venv\Scripts\python.exe -c "import app.main; print('ok')" 2>&1 | Add-Content "$out\checks.txt" -Encoding utf8
    $edited = @(git -c core.quotepath=false diff --name-only $before $after)
    "--- файлы, которые изменил Claude: $(if ($edited) { $edited -join ', ' } else { 'нет' })" | Add-Content "$out\checks.txt" -Encoding utf8
    if (Test-Path "tests\test_*.py") {
        "--- тесты: python tests/run.py" | Add-Content "$out\checks.txt" -Encoding utf8
        # unittest пишет в stderr — склеивает cmd, чтобы PowerShell не считал строки вывода ошибками
        cmd /c ".venv\Scripts\python.exe tests\run.py 2>&1" | Add-Content "$out\checks.txt" -Encoding utf8
    }
    if (Test-Path $check) {
        "--- проверка задачи: experiment\$($check.Substring($PSScriptRoot.Length + 1))" | Add-Content "$out\checks.txt" -Encoding utf8
        & .venv\Scripts\python.exe $check 2>$null | Add-Content "$out\checks.txt" -Encoding utf8
    }
} finally { Pop-Location; Remove-Item env:PROJECT_DIR, env:PYTHONUTF8 -ErrorAction SilentlyContinue }
Write-Host "Готово за $seconds с: experiment\$Name\ — result.md, changes.diff, checks.txt; копия проекта — $work"
