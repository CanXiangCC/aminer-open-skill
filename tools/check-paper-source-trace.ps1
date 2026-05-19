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

function Test-Structure {
    Add-Check "Skill SKILL.md exists" (Test-Path (Join-RepoPath "skills\paper-source-trace\SKILL.md")) "skills\paper-source-trace\SKILL.md"
    Add-Check "Command entry exists" (Test-Path (Join-RepoPath "skills\paper-source-trace\commands\paper-source-trace.md")) "skills\paper-source-trace\commands\paper-source-trace.md"
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
    }
    catch {
        Add-Check "evals.json parses" $false $_.Exception.Message
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
