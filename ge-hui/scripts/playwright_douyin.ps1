param(
    [ValidateSet("open", "snapshot", "collect", "resolve-media", "save-state", "close")]
    [string]$Action = "open",
    [string]$Session = "ge-hui-douyin",
    [string]$PrivateRoot = "",
    [string]$Selection = "",
    [string]$ResolvedOutput = "",
    [int]$Limit = 10
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if (-not $PrivateRoot) {
    $PrivateRoot = Join-Path $ProjectRoot "local-data\short-video"
}
if (-not $Selection) {
    $Selection = Join-Path $PrivateRoot "selection.jsonl"
}
if (-not $ResolvedOutput) {
    $ResolvedOutput = Join-Path $PrivateRoot "resolved-media.jsonl"
}
$AuthRoot = Join-Path (Split-Path $PrivateRoot -Parent) "auth"
New-Item -ItemType Directory -Force -Path $PrivateRoot, $AuthRoot | Out-Null

$Npx = "C:\Program Files\nodejs\npx.cmd"
if (-not (Test-Path $Npx)) {
    throw "npx is required. Install Node.js/npm before using this script."
}
$Base = @("--yes", "--package", "@playwright/cli", "playwright-cli", "--session", $Session)
$SearchUrl = "https://www.douyin.com/search/shibu71947?type=user"

switch ($Action) {
    "open" {
        & $Npx @Base open $SearchUrl --headed
        Write-Output "Complete the slider/login manually, open the expected profile, then run this script with -Action collect."
    }
    "snapshot" {
        & $Npx @Base snapshot
    }
    "collect" {
        # Keep JavaScript in single-quoted PowerShell variables. Backslash does not
        # escape a double quote in PowerShell, so inline \"...\" fragments are
        # split into multiple CLI arguments on Windows.
        $ScrollCode = 'async (page) => { await page.evaluate(async () => { window.__geHuiVideoLinks = Object(); const isWork = a => /\/video\//.test(a.href) && !a.closest(String.fromCharCode(102,111,111,116,101,114)); let stable = 0; let last = 0; for (let i = 0; i < 180 && stable < 8; i++) { for (const a of [...document.links].filter(isWork)) { window.__geHuiVideoLinks[a.href] = {url:a.href,title:(a.innerText||String()).trim()}; } const candidates = [...document.all].filter(e => e.scrollHeight > e.clientHeight + 500); const scroller = candidates.sort((a,b) => (b.scrollHeight-b.clientHeight)-(a.scrollHeight-a.clientHeight))[0] || document.scrollingElement; scroller.scrollTop = scroller.scrollHeight; await new Promise(r => setTimeout(r, 1500)); const count = Object.keys(window.__geHuiVideoLinks).length; stable = count === last ? stable + 1 : 0; last = count; } for (const a of [...document.links].filter(isWork)) { window.__geHuiVideoLinks[a.href] = {url:a.href,title:(a.innerText||String()).trim()}; } const candidates = [...document.all].filter(e => e.scrollHeight > e.clientHeight + 500); const scroller = candidates.sort((a,b) => (b.scrollHeight-b.clientHeight)-(a.scrollHeight-a.clientHeight))[0] || document.scrollingElement; scroller.scrollTop = 0; }); }'
        $ProfileExpr = '() => document.body.innerText'
        $LinksExpr = '() => Object.values(window.__geHuiVideoLinks||Object())'

        & $Npx @Base run-code $ScrollCode
        if ($LASTEXITCODE -ne 0) {
            throw "Playwright scrolling failed; refusing to save a partial inventory."
        }
        $Profile = & $Npx @Base --raw eval $ProfileExpr |
            Where-Object { $_ -notmatch '^Active code page:' }
        if ($LASTEXITCODE -ne 0) {
            throw "Playwright profile extraction failed."
        }
        $Links = & $Npx @Base --raw eval $LinksExpr |
            Where-Object { $_ -notmatch '^Active code page:' }
        if ($LASTEXITCODE -ne 0) {
            throw "Playwright link extraction failed."
        }
        $LinksText = $Links -join [Environment]::NewLine
        try {
            $ParsedLinks = $LinksText | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            throw "Playwright link extraction did not return valid JSON: $($_.Exception.Message)"
        }
        if (@($ParsedLinks).Count -lt 1) {
            throw "Playwright returned no video links; refusing to save an empty inventory."
        }
        $Profile | Set-Content -LiteralPath (Join-Path $PrivateRoot "profile-text.txt") -Encoding UTF8
        $LinksText | Set-Content -LiteralPath (Join-Path $PrivateRoot "playwright-links.json") -Encoding UTF8
        & $Npx @Base state-save (Join-Path $AuthRoot "douyin-storage-state.json")
        Write-Output "Collected profile text, video links, and private Playwright state. Run douyin_inventory.py next."
    }
    "resolve-media" {
        if (-not (Test-Path -LiteralPath $Selection)) {
            throw "Selection file not found: $Selection"
        }
        if ($Limit -lt 1) {
            throw "Limit must be positive."
        }
        $Records = Get-Content -LiteralPath $Selection | ForEach-Object { $_ | ConvertFrom-Json } |
            Where-Object { -not (Test-Path -LiteralPath (Join-Path $PrivateRoot "audio\$($_.video_id).flac")) } |
            Select-Object -First $Limit
        if (@($Records).Count -lt 1) {
            throw "Selection is empty."
        }

        $WaitCode = 'async (page) => { await page.waitForFunction(() => [...document.all].some(e => /^VIDEO$/.test(e.tagName) && e.currentSrc && e.readyState >= 2), null, {timeout:30000}); }'
        $MediaExpr = '() => [...document.all].filter(e => /^VIDEO$/.test(e.tagName) && e.currentSrc && e.readyState >= 2).map(v => ({media_url:v.currentSrc,duration_seconds:v.duration,ready_state:v.readyState,user_agent:navigator.userAgent}))'
        $CaptureCode = 'async (page) => { const urls=[]; page.on(String.fromCharCode(114,101,115,112,111,110,115,101), async r => { try { const h=await r.allHeaders(); if(Object.values(h).some(v=>/video|audio|octet-stream/.test(v)) && /douyinvod|bytev/.test(r.url())) urls.push(r.url()); } catch(e) {} }); await page.reload(); await page.waitForTimeout(8000); await page.evaluate(u=>Object.assign(window,{__geHuiMediaResponses:[...new Set(u)]}),urls); }'
        $ResponseExpr = '() => window.__geHuiMediaResponses||[]'
        $Resolved = @()

        foreach ($Record in $Records) {
            $Opened = $false
            try {
                & $Npx @Base tab-new $Record.source_url
                if ($LASTEXITCODE -ne 0) {
                    throw "Failed to open video $($Record.video_id)."
                }
                $Opened = $true
                & $Npx @Base run-code $WaitCode
                if ($LASTEXITCODE -ne 0) {
                    throw "Video media did not become ready for $($Record.video_id); stop for manual review."
                }
                $Raw = & $Npx @Base --raw eval $MediaExpr |
                    Where-Object { $_ -notmatch '^Active code page:' }
                if ($LASTEXITCODE -ne 0) {
                    throw "Failed to read media URL for $($Record.video_id)."
                }
                $Media = @($Raw -join [Environment]::NewLine | ConvertFrom-Json)
                if ($Media.Count -lt 1) {
                    throw "No playable media URL found for $($Record.video_id); stop for manual review."
                }
                $MediaUrls = @($Media | ForEach-Object { [string]$_.media_url } | Where-Object { $_ -notmatch '^blob:' })
                $Method = "playwright-currentSrc"
                if ($MediaUrls.Count -lt 1) {
                    & $Npx @Base run-code $CaptureCode
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to capture browser media responses for blob video $($Record.video_id)."
                    }
                    $ResponseRaw = & $Npx @Base --raw eval $ResponseExpr |
                        Where-Object { $_ -notmatch '^Active code page:' }
                    if ($LASTEXITCODE -ne 0) {
                        throw "Failed to read captured media responses for $($Record.video_id)."
                    }
                    $MediaUrls = @($ResponseRaw -join [Environment]::NewLine | ConvertFrom-Json)
                    $Method = "playwright-response"
                }
                if ($MediaUrls.Count -lt 1) {
                    throw "No downloadable browser media response found for $($Record.video_id)."
                }
                $Resolved += [pscustomobject]@{
                    video_id = [string]$Record.video_id
                    source_url = [string]$Record.source_url
                    media_url = [string]$MediaUrls[0]
                    media_urls = @($MediaUrls)
                    duration_seconds = [double]$Media[0].duration_seconds
                    user_agent = [string]$Media[0].user_agent
                    resolved_on = [DateTime]::UtcNow.ToString("o")
                    method = $Method
                }
                Write-Output "$($Record.video_id): media-resolved"
            }
            finally {
                if ($Opened) {
                    & $Npx @Base tab-close | Out-Null
                }
            }
            Start-Sleep -Seconds (Get-Random -Minimum 3 -Maximum 9)
        }

        $ResolvedText = ($Resolved | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 5 }) -join "`n"
        if ($ResolvedText) {
            $ResolvedText += "`n"
        }
        $ResolvedText | Set-Content -LiteralPath $ResolvedOutput -Encoding UTF8 -NoNewline
        Write-Output "Resolved $($Resolved.Count) browser-loaded media URLs to private storage."
    }
    "save-state" {
        & $Npx @Base state-save (Join-Path $AuthRoot "douyin-storage-state.json")
    }
    "close" {
        & $Npx @Base close
    }
}
