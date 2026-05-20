param(
    [switch]$NoTokenStatus
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SkillRoot = Join-Path $RepoRoot "skills\paper-source-trace"
$Checks = @()

function Add-Check {
    param(
        [string]$Name,
        [bool]$Passed,
        [string]$Message
    )

    $script:Checks += [PSCustomObject]@{
        Name = $Name
        Passed = $Passed
        Message = $Message
    }
}

function Join-RepoPath {
    param([string]$RelativePath)
    return Join-Path $RepoRoot $RelativePath
}

function Has-Property {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $false
    }
    return ($Object.PSObject.Properties.Name -contains $Name)
}

function Is-NonEmptyString {
    param([object]$Value)
    return ($null -ne $Value -and -not [string]::IsNullOrWhiteSpace([string]$Value))
}

function Get-HashPrefix {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hash = $sha.ComputeHash($bytes)
        $hex = ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
        return $hex.Substring(0, 12).ToUpperInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-TokenRows {
    $name = "AMINER_API_KEY"
    $rows = @()

    foreach ($scope in @("Process", "User", "Machine")) {
        $value = [Environment]::GetEnvironmentVariable($name, $scope)
        $rows += [PSCustomObject]@{
            Scope = $scope
            Configured = -not [string]::IsNullOrWhiteSpace($value)
            Length = if ($value) { $value.Length } else { 0 }
            Sha256Prefix = Get-HashPrefix $value
        }
    }

    return $rows
}

function Get-LayoutOverlapCount {
    param([object[]]$Nodes)

    $count = 0
    for ($i = 0; $i -lt $Nodes.Count; $i++) {
        for ($j = $i + 1; $j -lt $Nodes.Count; $j++) {
            $a = $Nodes[$i]
            $b = $Nodes[$j]
            $overlapX = [Math]::Max(0, [Math]::Min(($a.x + $a.w), ($b.x + $b.w)) - [Math]::Max($a.x, $b.x))
            $overlapY = [Math]::Max(0, [Math]::Min(($a.y + $a.h), ($b.y + $b.h)) - [Math]::Max($a.y, $b.y))
            if ($overlapX -gt 0 -and $overlapY -gt 0) {
                $count++
            }
        }
    }

    return $count
}

function Test-Structure {
    Add-Check "Skill SKILL.md exists" (Test-Path (Join-RepoPath "skills\paper-source-trace\SKILL.md")) "skills\paper-source-trace\SKILL.md"
    Add-Check "Command entry exists" (Test-Path (Join-RepoPath "skills\paper-source-trace\commands\paper-source-trace.md")) "skills\paper-source-trace\commands\paper-source-trace.md"
    Add-Check "HTML renderer exists" (Test-Path (Join-RepoPath "skills\paper-source-trace\scripts\render_html.py")) "skills\paper-source-trace\scripts\render_html.py"
    Add-Check "Old skill directory absent" (-not (Test-Path (Join-RepoPath "skills\paper-citation-map"))) "skills\paper-citation-map should not exist"
    Add-Check "Skill usage guide exists" (Test-Path (Join-RepoPath "skills\paper-source-trace\README.md")) "skills\paper-source-trace\README.md"
}

function Test-Marketplace {
    $path = Join-RepoPath ".claude-plugin\marketplace.json"
    try {
        $json = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
        Add-Check "marketplace.json parses" $true ".claude-plugin\marketplace.json"

        $entry = @($json.plugins) | Where-Object { $_.name -eq "paper-source-trace" } | Select-Object -First 1
        Add-Check "marketplace has paper-source-trace" ($null -ne $entry) "plugin name paper-source-trace"

        if ($null -ne $entry) {
            $sourceOk = ($entry.source -eq "./skills/paper-source-trace")
            Add-Check "marketplace source is correct" $sourceOk $entry.source

            $sourcePath = Join-RepoPath ($entry.source -replace "^\.\/", "")
            Add-Check "marketplace source path exists" (Test-Path $sourcePath) $sourcePath
        }
    }
    catch {
        Add-Check "marketplace.json parses" $false $_.Exception.Message
    }
}

function Test-Schema {
    $path = Join-RepoPath "skills\paper-source-trace\references\schema.md"

    try {
        $text = Get-Content -Raw -Encoding UTF8 $path
        Add-Check "schema mentions json/graph output path" ($text -match "json/graph/citation_graph\.json") "json/graph/citation_graph.json"

        $matches = [regex]::Matches($text, '(?s)```json\s*(.*?)```')
        Add-Check "schema has JSON code blocks" ($matches.Count -gt 0) "$($matches.Count) JSON block(s)"

        $objects = @()
        foreach ($match in $matches) {
            $raw = $match.Groups[1].Value.Trim()
            try {
                $objects += ($raw | ConvertFrom-Json)
            }
            catch {
                Add-Check "schema JSON block parses" $false $_.Exception.Message
            }
        }

        if ($objects.Count -gt 0) {
            Add-Check "schema JSON blocks parse" $true "$($objects.Count) parsed block(s)"
        }

        $example = $objects | Where-Object {
            (Has-Property $_ "schema_version") -and
            ($_.schema_version -eq "0.3.0") -and
            (Has-Property $_ "source_traces") -and
            (@($_.source_traces).Count -gt 0)
        } | Select-Object -First 1

        Add-Check "schema minimal example version is 0.3.0" ($null -ne $example) "schema_version 0.3.0 with source_traces[]"

        if ($null -ne $example) {
            $citationOk = $true
            foreach ($citation in @($example.citations)) {
                $hasRequired = (Has-Property $citation "intent") -and
                    (Has-Property $citation "evidence") -and
                    (Has-Property $citation "confidence")
                $hasReference = ((Has-Property $citation "reference_id") -and (Is-NonEmptyString $citation.reference_id)) -or
                    ((Has-Property $citation "unmatched_reference") -and ($citation.unmatched_reference -eq $true))
                if (-not ($hasRequired -and $hasReference)) {
                    $citationOk = $false
                }
            }
            Add-Check "example citations have required fields" $citationOk "intent, evidence, confidence, reference_id or unmatched_reference"

            $stepsOk = $true
            foreach ($trace in @($example.source_traces)) {
                foreach ($step in @($trace.source_steps)) {
                    $hasLinks = (Has-Property $step "citation_id") -and
                        (Is-NonEmptyString $step.citation_id) -and
                        (Has-Property $step "reference_id") -and
                        (Is-NonEmptyString $step.reference_id)
                    if (-not $hasLinks) {
                        $stepsOk = $false
                    }
                }
            }
            Add-Check "source steps link citations and references" $stepsOk "citation_id and reference_id"

            $strategyOk = (Has-Property $example "metadata") -and
                (Has-Property $example.metadata "source_trace") -and
                (Has-Property $example.metadata.source_trace "strategy") -and
                ($example.metadata.source_trace.strategy -eq "claim-centered")
            Add-Check "metadata.source_trace strategy is claim-centered" $strategyOk "metadata.source_trace.strategy"
        }
    }
    catch {
        Add-Check "schema validation" $false $_.Exception.Message
    }
}

function Test-Evals {
    $path = Join-RepoPath "skills\paper-source-trace\evals\evals.json"

    try {
        $json = Get-Content -Raw -Encoding UTF8 $path | ConvertFrom-Json
        Add-Check "evals.json parses" $true "skills\paper-source-trace\evals\evals.json"
        Add-Check "eval skill_name is paper-source-trace" ($json.skill_name -eq "paper-source-trace") $json.skill_name

        $prompts = (@($json.evals) | ForEach-Object { $_.prompt }) -join "`n"
        $evalText = (@($json.evals) | ForEach-Object {
            @($_.prompt, $_.expected_output, (@($_.expectations) -join "`n")) -join "`n"
        }) -join "`n"
        Add-Check "evals cover slash command" ($prompts -match "/paper-source-trace") "slash command prompt"
        Add-Check "evals cover aminer:on" ($prompts -match "aminer:on") "AMiner opt-in command prompt"
        Add-Check "evals cover json/graph output path" ($evalText -match "json/graph/citation_graph\.json") "json/graph/citation_graph.json"
        Add-Check "evals cover HTML graph output" ($evalText -match "citation_map\.html") "citation_map.html"
        Add-Check "evals cover standard graph renderer" ($evalText -match "scripts/render_html\.py" -and $evalText -match "--svg both") "scripts/render_html.py --svg both"
        Add-Check "evals cover HTML interaction controls" ($evalText -match "zoom" -and $evalText -match "drag") "zoom and drag"
        Add-Check "evals cover unified SVG and HTML rendering" ($evalText -match "canonical groups" -and $evalText -match "reduced-edge|edge") "unified SVG/HTML visual contract"
    }
    catch {
        Add-Check "evals.json parses" $false $_.Exception.Message
    }
}

function Test-HtmlRenderer {
    $rendererPath = Join-RepoPath "skills\paper-source-trace\scripts\render_html.py"

    if (-not (Test-Path $rendererPath)) {
        Add-Check "HTML renderer validation" $false "scripts\render_html.py is missing"
        return
    }

    try {
        $rendererText = Get-Content -Raw -Encoding UTF8 $rendererPath
        Add-Check "graph renderer uses explicit quote escaping" ($rendererText -match 'return "&quot;"') "esc() quote branch"
        Add-Check "graph renderer wraps non-spaced text" ($rendererText -match "Array\.from\(raw\)" -and $rendererText -match "def text_parts") "CJK-friendly text wrapping"
        Add-Check "graph renderer supports SVG CLI" ($rendererText -match "--svg" -and $rendererText -match "render_svg") "--svg and render_svg"

        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $python) {
            Add-Check "HTML renderer Python compile" $false "python not found"
            return
        }

        $syntaxOutput = & $python.Source -c "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'), filename=sys.argv[1])" $rendererPath 2>&1
        Add-Check "HTML renderer Python syntax" ($LASTEXITCODE -eq 0) (($syntaxOutput | Out-String).Trim())

        $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("paper-source-trace-check-" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

        try {
            $graphDir = Join-Path $tempRoot "json\graph"
            New-Item -ItemType Directory -Force -Path $graphDir | Out-Null
            $graphPath = Join-Path $graphDir "citation_graph.json"
            $htmlPath = Join-Path $tempRoot "citation_map.html"
            $svgPath = Join-Path $tempRoot "citation_map.svg"
            $chainSvgPath = Join-Path $tempRoot "citation_map_chain.svg"

            $sample = @{
                schema_version = "0.3.0"
                paper = @{
                    paper_id = "target-paper"
                    title = "Sample Paper"
                    year = 2026
                }
                references = @(
                    @{
                        reference_id = "ref-001"
                        title = "Reference"
                        authors = @("A")
                        year = 2025
                    }
                )
                citations = @(
                    @{
                        citation_id = "cit-001"
                        reference_id = "ref-001"
                        marker = "(A, 2025)"
                        intent = "background"
                        evidence = "Sample evidence for HTML rendering."
                        confidence = 0.9
                        trace_ids = @("trace-001")
                    }
                    @{
                        citation_id = "cit-002"
                        reference_id = "ref-001"
                        marker = "(A, 2025)"
                        intent = "core-method"
                        evidence = "Method evidence for HTML rendering."
                        confidence = 0.8
                        trace_ids = @("trace-001")
                    }
                    @{
                        citation_id = "cit-003"
                        reference_id = "ref-001"
                        marker = "(A, 2025)"
                        intent = "dataset"
                        evidence = "Dataset evidence for HTML rendering."
                        confidence = 0.8
                        trace_ids = @("trace-001")
                    }
                    @{
                        citation_id = "cit-004"
                        reference_id = "ref-001"
                        marker = "(A, 2025)"
                        intent = "baseline"
                        evidence = "Baseline evidence for HTML rendering."
                        confidence = 0.8
                        trace_ids = @("trace-001")
                    }
                    @{
                        citation_id = "cit-005"
                        reference_id = "ref-001"
                        marker = "(A, 2025)"
                        intent = "limitation"
                        evidence = "Limitation evidence for HTML rendering."
                        confidence = 0.8
                        trace_ids = @("trace-001")
                    }
                )
                source_traces = @(
                    @{
                        trace_id = "trace-001"
                        claim_id = "claim-001"
                        target_claim = "Sample claim"
                        claim_type = "contribution"
                        summary = "Sample source trace."
                        source_steps = @(
                            @{
                                citation_id = "cit-001"
                                reference_id = "ref-001"
                                source_role = "foundation"
                                intent = "background"
                                relation_type = "supports"
                                evidence = "Sample evidence"
                                confidence = 0.9
                            }
                        )
                        confidence = 0.9
                    }
                )
                visual_groups = @(
                    @{
                        group_id = "background"
                        label = "Background"
                        intent_filters = @("background")
                        node_ids = @("cit-001")
                        color = "#cf6f6f"
                    }
                )
                metadata = @{
                    output_language = "zh"
                    source_trace = @{
                        enabled = $true
                        strategy = "claim-centered"
                    }
                }
            }

            $utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
            [System.IO.File]::WriteAllText($graphPath, ($sample | ConvertTo-Json -Depth 20), $utf8NoBom)
            $renderOutput = & $python.Source $rendererPath --graph $graphPath --output $htmlPath --svg both --svg-output $svgPath --chain-output $chainSvgPath --language auto 2>&1
            $renderOk = ($LASTEXITCODE -eq 0) -and (Test-Path $htmlPath) -and (Test-Path $svgPath) -and (Test-Path $chainSvgPath)
            Add-Check "HTML renderer sample render" $renderOk (($renderOutput | Out-String).Trim())

            if ($renderOk) {
                $htmlText = Get-Content -Raw -Encoding UTF8 $htmlPath
                $svgText = Get-Content -Raw -Encoding UTF8 $svgPath
                $chainSvgText = Get-Content -Raw -Encoding UTF8 $chainSvgPath
                $zhRadial = -join @([char]0x5F84, [char]0x5411, [char]0x56FE)
                $zhChain = -join @([char]0x6EAF, [char]0x6E90, [char]0x94FE, [char]0x56FE)
                $zhReset = -join @([char]0x91CD, [char]0x7F6E, [char]0x5E03, [char]0x5C40)
                $zhProblemChain = -join @([char]0x95EE, [char]0x9898, [char]0x94FE)
                $zhMethodChain = -join @([char]0x65B9, [char]0x6CD5, [char]0x94FE)
                $zhDataChain = -join @([char]0x6570, [char]0x636E, [char]0x94FE)
                $zhBaselineChain = -join @([char]0x57FA, [char]0x7EBF, [char]0x94FE)
                $zhLimitResourceChain = -join @([char]0x5C40, [char]0x9650, [char]0x2F, [char]0x8D44, [char]0x6E90, [char]0x94FE)
                Add-Check "sample HTML has unified Chinese controls" ($htmlText -match [regex]::Escape($zhRadial) -and $htmlText -match [regex]::Escape($zhChain) -and $htmlText -match [regex]::Escape($zhReset)) "zh controls"
                Add-Check "sample HTML embeds graph data" ($htmlText -match 'id="graph-data"' -and $htmlText -match "citation_graph\.json") "embedded JSON and subtitle"
                $svgXmlOk = $true
                try {
                    [xml]$null = $svgText
                    [xml]$null = $chainSvgText
                }
                catch {
                    $svgXmlOk = $false
                }
                Add-Check "sample SVG files parse as XML" $svgXmlOk "citation_map.svg and citation_map_chain.svg"
                Add-Check "sample chain SVG uses Chinese chain hubs" ($chainSvgText -match [regex]::Escape($zhProblemChain) -and $chainSvgText -match [regex]::Escape($zhMethodChain) -and $chainSvgText -match [regex]::Escape($zhDataChain) -and $chainSvgText -match [regex]::Escape($zhBaselineChain) -and $chainSvgText -match [regex]::Escape($zhLimitResourceChain)) "Chinese chain hub labels"
                Add-Check "sample Chinese SVG avoids English UI labels" (-not ($chainSvgText -cmatch "Target Paper|Problem chain|Method chain|Data chain|Baseline chain|Limits/resources chain")) "no mixed English SVG labels"
                $chainEdgeCount = ([regex]::Matches($chainSvgText, '<path class="edge"')).Count
                Add-Check "sample chain SVG uses reduced edge count" ($chainEdgeCount -le 15) "$chainEdgeCount edge paths"

                $radialRects = @([regex]::Matches($svgText, '<g class="node[^"]*">\s*<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"') | ForEach-Object {
                    [PSCustomObject]@{
                        x = [double]$_.Groups[1].Value
                        y = [double]$_.Groups[2].Value
                        w = [double]$_.Groups[3].Value
                        h = [double]$_.Groups[4].Value
                    }
                })
                $chainRects = @([regex]::Matches($chainSvgText, '<g class="node[^"]*">\s*<rect x="([0-9.]+)" y="([0-9.]+)" width="([0-9.]+)" height="([0-9.]+)"') | ForEach-Object {
                    [PSCustomObject]@{
                        x = [double]$_.Groups[1].Value
                        y = [double]$_.Groups[2].Value
                        w = [double]$_.Groups[3].Value
                        h = [double]$_.Groups[4].Value
                    }
                })
                $radialOverlapCount = Get-LayoutOverlapCount $radialRects
                $chainOverlapCount = Get-LayoutOverlapCount $chainRects
                Add-Check "sample SVG node layouts avoid overlap" (($radialOverlapCount + $chainOverlapCount) -eq 0) "radial=$radialOverlapCount chain=$chainOverlapCount"

                $scripts = [regex]::Matches($htmlText, '(?s)<script(?![^>]*application/json)[^>]*>(.*?)</script>')
                Add-Check "sample HTML has executable inline script" ($scripts.Count -gt 0) "$($scripts.Count) script block(s)"

                $node = Get-Command node -ErrorAction SilentlyContinue
                if (($null -ne $node) -and ($scripts.Count -gt 0)) {
                    $jsPath = Join-Path $tempRoot "citation_map.inline.js"
                    [System.IO.File]::WriteAllText($jsPath, $scripts[0].Groups[1].Value, $utf8NoBom)
                    $nodeOutput = & $node.Source --check $jsPath 2>&1
                    Add-Check "sample HTML JavaScript syntax" ($LASTEXITCODE -eq 0) (($nodeOutput | Out-String).Trim())
                }
                else {
                    Add-Check "sample HTML JavaScript syntax" $true "node not found; skipped"
                }
            }
        }
        finally {
            if (Test-Path $tempRoot) {
                Remove-Item -LiteralPath $tempRoot -Recurse -Force
            }
        }
    }
    catch {
        Add-Check "HTML renderer validation" $false $_.Exception.Message
    }
}

function Test-DocsAndOldSlug {
    $requiredFiles = @(
        "README.md",
        "README.zh.md",
        "skills\paper-source-trace\README.md",
        "skills\paper-source-trace\SKILL.md",
        "skills\paper-source-trace\commands\paper-source-trace.md"
    )

    foreach ($relativePath in $requiredFiles) {
        $path = Join-RepoPath $relativePath
        try {
            $text = Get-Content -Raw -Encoding UTF8 $path
            Add-Check "$relativePath mentions /paper-source-trace" ($text -match "/paper-source-trace") "/paper-source-trace"
            Add-Check "$relativePath explains token optionality" ($text -match "AMINER_API_KEY" -and $text -match "token") "AMINER_API_KEY and token"
            Add-Check "$relativePath explains AMiner opt-in" ($text -match "AMiner" -and ($text -match "opt-in|explicit|aminer:\s*on")) "AMiner explicit opt-in"
            Add-Check "$relativePath mentions json/graph output" ($text -match "json/graph/citation_graph\.json") "json/graph/citation_graph.json"
            Add-Check "$relativePath mentions HTML graph" ($text -match "citation_map\.html") "citation_map.html"
        }
        catch {
            Add-Check "$relativePath readable" $false $_.Exception.Message
        }
    }

    $visualPath = Join-RepoPath "skills\paper-source-trace\references\visual.md"
    try {
        $visualText = Get-Content -Raw -Encoding UTF8 $visualPath
        Add-Check "visual reference defines HTML graph" ($visualText -match "citation_map\.html" -and $visualText -match "single-file") "citation_map.html single-file"
        Add-Check "visual reference requires graph renderer" ($visualText -match "scripts/render_html\.py" -and $visualText -match "SVG" -and $visualText -match "HTML") "scripts/render_html.py for SVG and HTML"
        Add-Check "visual reference defines HTML interaction controls" ($visualText -match "zoom" -and $visualText -match "drag") "zoom and drag"
        Add-Check "visual reference defines reduced SVG edges" ($visualText -match "reduced" -and $visualText -match "cross-link") "reduced SVG edges"
    }
    catch {
        Add-Check "visual reference readable" $false $_.Exception.Message
    }

    $templatePath = Join-RepoPath "skills\paper-source-trace\references\analysis_template.md"
    try {
        $templateText = Get-Content -Raw -Encoding UTF8 $templatePath
        Add-Check "analysis template lists json/graph output" ($templateText -match "json/graph/citation_graph\.json") "json/graph/citation_graph.json"
        Add-Check "analysis template lists HTML output" ($templateText -match "citation_map\.html") "citation_map.html"
    }
    catch {
        Add-Check "analysis template readable" $false $_.Exception.Message
    }

    $targets = @(
        Join-RepoPath "README.md",
        Join-RepoPath "README.zh.md",
        Join-RepoPath ".claude-plugin",
        Join-RepoPath "skills"
    )

    $oldHits = @()
    foreach ($target in $targets) {
        if (Test-Path $target -PathType Leaf) {
            $files = @((Get-Item $target))
        }
        else {
            $files = @(Get-ChildItem -Path $target -Recurse -File -ErrorAction Stop)
        }

        foreach ($file in $files) {
            try {
                $content = Get-Content -Raw -Encoding UTF8 $file.FullName
                if ($content -match "paper-citation-map|Paper Citation Map") {
                    $oldHits += $file.FullName.Substring($RepoRoot.Length + 1)
                }
            }
            catch {
                # Ignore unreadable binary or host-specific files outside the text surface.
            }
        }
    }

    Add-Check "no old Paper Citation Map slug in README, marketplace, skills" ($oldHits.Count -eq 0) (($oldHits | Sort-Object -Unique) -join ", ")
}

function Test-TextQuality {
    $targets = @(
        Join-RepoPath "README.md",
        Join-RepoPath "README.zh.md",
        Join-RepoPath ".claude-plugin",
        $SkillRoot
    )

    $badHits = @()
    $placeholderHits = @()
    $placeholderPattern = (@("TO" + "DO", "T" + "BD", "FIX" + "ME") -join "|")
    foreach ($target in $targets) {
        if (Test-Path $target -PathType Leaf) {
            $files = @((Get-Item $target))
        }
        else {
            $files = @(Get-ChildItem -Path $target -Recurse -File -ErrorAction Stop)
        }

        foreach ($file in $files) {
            try {
                $content = Get-Content -Raw -Encoding UTF8 $file.FullName
                $relative = $file.FullName.Substring($RepoRoot.Length + 1)
                if ($content -match [char]0xFFFD) {
                    $badHits += $relative
                }
                if ($content -match $placeholderPattern) {
                    $placeholderHits += $relative
                }
            }
            catch {
                # Ignore unreadable binary or host-specific files outside the text surface.
            }
        }
    }

    Add-Check "no replacement character in docs and skill" ($badHits.Count -eq 0) (($badHits | Sort-Object -Unique) -join ", ")
    Add-Check "no placeholder markers in docs and skill" ($placeholderHits.Count -eq 0) (($placeholderHits | Sort-Object -Unique) -join ", ")
}

Write-Host "Paper Source Trace local check"
Write-Host "Repo: $RepoRoot"
Write-Host ""

Test-Structure
Test-Marketplace
Test-Schema
Test-Evals
Test-HtmlRenderer
Test-DocsAndOldSlug
Test-TextQuality

foreach ($check in $Checks) {
    $prefix = if ($check.Passed) { "[PASS]" } else { "[FAIL]" }
    Write-Host "$prefix $($check.Name) - $($check.Message)"
}

Write-Host ""
if (-not $NoTokenStatus) {
    Write-Host "AMINER_API_KEY status (token value is never printed):"
    Get-TokenRows | Format-Table -AutoSize
}

$failed = @($Checks | Where-Object { -not $_.Passed })
$passedCount = @($Checks | Where-Object { $_.Passed }).Count
$failedCount = $failed.Count

Write-Host "Summary: $passedCount passed, $failedCount failed."

if ($failedCount -gt 0) {
    exit 1
}

exit 0
