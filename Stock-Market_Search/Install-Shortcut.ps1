# ============================================================
#  Install-Shortcut.ps1
#  Run this ONCE to place "Antigravity TradeAI" on your Desktop
#  Right-click → Run with PowerShell
# ============================================================

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "   Antigravity TradeAI — Shortcut Installer" -ForegroundColor Cyan
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Paths ──────────────────────────────────────────────────
$root       = Split-Path -Parent $MyInvocation.MyCommand.Path
$batFile    = Join-Path $root "TradeAI.bat"
$desktop    = [System.Environment]::GetFolderPath("Desktop")
$shortcut   = Join-Path $desktop "Antigravity TradeAI.lnk"
$iconFile   = Join-Path $root "icon.ico"

# ── Verify launcher exists ─────────────────────────────────
if (-not (Test-Path $batFile)) {
    Write-Host "  [!] ERROR: TradeAI.bat not found at $batFile" -ForegroundColor Red
    Write-Host "      Make sure you run this script from the project folder." -ForegroundColor Red
    Read-Host "  Press Enter to exit"
    exit 1
}

# ── Download a stock-chart icon if none exists ─────────────
if (-not (Test-Path $iconFile)) {
    Write-Host "  [*] Generating app icon..." -ForegroundColor Yellow
    try {
        # Create a minimal valid .ico using a PowerShell-drawn bitmap
        Add-Type -AssemblyName System.Drawing

        $size   = 64
        $bmp    = New-Object System.Drawing.Bitmap($size, $size)
        $g      = [System.Drawing.Graphics]::FromImage($bmp)

        # Dark background
        $g.Clear([System.Drawing.Color]::FromArgb(255, 13, 17, 23))

        # Draw a simple candlestick-style chart
        $green  = [System.Drawing.Color]::FromArgb(255, 0, 230, 118)
        $red    = [System.Drawing.Color]::FromArgb(255, 255, 23, 68)
        $white  = [System.Drawing.Color]::FromArgb(255, 240, 246, 252)

        $pGreen = New-Object System.Drawing.SolidBrush($green)
        $pRed   = New-Object System.Drawing.SolidBrush($red)
        $pen    = New-Object System.Drawing.Pen($white, 1)

        # Bars (simple bar chart)
        $bars = @(
            @{x=6;  y=40; h=20; c=$green},
            @{x=16; y=30; h=30; c=$red},
            @{x=26; y=20; h=40; c=$green},
            @{x=36; y=35; h=25; c=$red},
            @{x=46; y=10; h=50; c=$green}
        )
        foreach ($b in $bars) {
            $br = New-Object System.Drawing.SolidBrush($b.c)
            $g.FillRectangle($br, $b.x, $b.y, 8, $b.h)
            $br.Dispose()
        }

        # Trend line
        $tPen = New-Object System.Drawing.Pen($green, 2)
        $pts  = @(
            [System.Drawing.Point]::new(6,  52),
            [System.Drawing.Point]::new(20, 42),
            [System.Drawing.Point]::new(30, 35),
            [System.Drawing.Point]::new(40, 28),
            [System.Drawing.Point]::new(54, 14)
        )
        $g.DrawLines($tPen, $pts)

        $g.Dispose()
        $tPen.Dispose()
        $pGreen.Dispose()
        $pRed.Dispose()
        $pen.Dispose()

        # Save as .ico (write raw ICO header + BMP pixel data)
        $ms  = New-Object System.IO.MemoryStream
        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngBytes = $ms.ToArray()
        $ms.Dispose()
        $bmp.Dispose()

        # ICO file structure (single 64x64 PNG image inside)
        $icoHeader = [byte[]]@(
            0x00, 0x00,         # Reserved
            0x01, 0x00,         # Type: 1 = ICO
            0x01, 0x00          # Count: 1 image
        )
        $imgEntry = [byte[]]@(
            0x40,               # Width  = 64
            0x40,               # Height = 64
            0x00,               # ColorCount = 0 (no palette)
            0x00,               # Reserved
            0x01, 0x00,         # ColorPlanes
            0x20, 0x00,         # BitsPerPixel = 32
            # ImageSize (4 bytes LE)
            ($pngBytes.Length -band 0xFF),
            (($pngBytes.Length -shr 8) -band 0xFF),
            (($pngBytes.Length -shr 16) -band 0xFF),
            (($pngBytes.Length -shr 24) -band 0xFF),
            # Offset = 6 (header) + 16 (entry) = 22
            0x16, 0x00, 0x00, 0x00
        )
        $icoBytes = $icoHeader + $imgEntry + $pngBytes
        [System.IO.File]::WriteAllBytes($iconFile, $icoBytes)
        Write-Host "  [+] Icon created: $iconFile" -ForegroundColor Green
    } catch {
        Write-Host "  [!] Icon generation skipped: $_" -ForegroundColor DarkYellow
        $iconFile = $null
    }
}

# ── Create the desktop shortcut ────────────────────────────
Write-Host "  [*] Creating desktop shortcut..." -ForegroundColor Yellow

$wsh = New-Object -ComObject WScript.Shell
$lnk = $wsh.CreateShortcut($shortcut)
$lnk.TargetPath       = $batFile
$lnk.WorkingDirectory = $root
$lnk.Description      = "Antigravity TradeAI — Hybrid Expert Trading System"
$lnk.WindowStyle      = 1   # Normal window

if ($iconFile -and (Test-Path $iconFile)) {
    $lnk.IconLocation = "$iconFile,0"
}

$lnk.Save()

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host "   [OK] Shortcut created on Desktop!" -ForegroundColor Green
Write-Host ""
Write-Host "   Double-click  'Antigravity TradeAI'  on your Desktop" -ForegroundColor White
Write-Host "   to launch the app at any time — no terminal needed." -ForegroundColor White
Write-Host "  ============================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "  Press Enter to close"
