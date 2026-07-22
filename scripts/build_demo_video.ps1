$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontendRoot = Join-Path $repoRoot 'frontend'
$demoRoot = Join-Path $repoRoot 'docs\assets\demo'
$webmPath = Join-Path $demoRoot 'invoice-review-demo.webm'
$mp4Path = Join-Path $demoRoot 'invoice-review-demo.mp4'
$toolRoot = Join-Path $env:TEMP 'invoice-review-video-tools'
$ffmpegPath = Join-Path $toolRoot 'node_modules\ffmpeg-static\ffmpeg.exe'

Push-Location $frontendRoot
try {
    npm run capture:demo
    if ($LASTEXITCODE -ne 0) {
        throw 'Playwright demo recording failed.'
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $ffmpegPath)) {
    npm install --prefix $toolRoot --no-save --package-lock=false ffmpeg-static@5.2.0
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to install the temporary FFmpeg binary.'
    }
}

& $ffmpegPath `
    -loglevel warning `
    -y `
    -i $webmPath `
    -c:v libx264 `
    -preset medium `
    -crf 24 `
    -pix_fmt yuv420p `
    -movflags +faststart `
    -an `
    $mp4Path

if ($LASTEXITCODE -ne 0) {
    throw 'FFmpeg conversion failed.'
}

$video = Get-Item -LiteralPath $mp4Path
Write-Host "Demo video ready: $($video.FullName) ($([Math]::Round($video.Length / 1MB, 2)) MiB)"
