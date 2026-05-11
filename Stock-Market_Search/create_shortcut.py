"""
Antigravity TradeAI - Desktop Shortcut Creator
===============================================
Run this ONCE with Python to place a clickable icon on your Desktop.
  > python create_shortcut.py
"""

import os
import sys
import struct
import subprocess
from pathlib import Path

ROOT      = Path(__file__).parent.resolve()
BAT_FILE  = ROOT / "TradeAI.bat"
ICON_FILE = ROOT / "icon.ico"
DESKTOP   = Path.home() / "Desktop"
SHORTCUT  = DESKTOP / "Antigravity TradeAI.lnk"


# ─── Step 1: Generate a simple ICO icon using only stdlib ────────────────────

def make_icon():
    """Build a 32x32 .ico from scratch using struct (no Pillow needed)."""
    if ICON_FILE.exists():
        return

    SIZE = 32
    # Create raw BGRA pixel data for a dark chart icon
    pixels = []
    for row in range(SIZE):
        for col in range(SIZE):
            # Dark background
            b, g, r, a = 23, 17, 13, 255

            # Green trend line (diagonal from bottom-left to top-right)
            line_row = SIZE - 1 - col
            if abs(row - line_row) <= 1:
                b, g, r, a = 0, 230, 118, 255

            # White candlestick bodies (5 bars)
            bar_cols = [4, 9, 14, 19, 24]
            bar_heights = [8, 14, 10, 18, 24]   # heights from bottom
            for i, bc in enumerate(bar_cols):
                bh = bar_heights[i]
                if bc <= col <= bc + 3:
                    bar_top = SIZE - bh
                    # Color: green or red alternating
                    is_green = (i % 2 == 0)
                    if row >= bar_top:
                        if is_green:
                            b, g, r, a = 0, 180, 80, 255
                        else:
                            b, g, r, a = 50, 30, 220, 255

            pixels.append(struct.pack("4B", b, g, r, a))

    raw_pixels = b"".join(pixels)

    # BMP DIB header (BITMAPINFOHEADER = 40 bytes)
    bmp_data  = struct.pack("<I", 40)           # header size
    bmp_data += struct.pack("<i", SIZE)         # width
    bmp_data += struct.pack("<i", SIZE * 2)     # height (doubled for ICO mask)
    bmp_data += struct.pack("<H", 1)            # color planes
    bmp_data += struct.pack("<H", 32)           # bits per pixel
    bmp_data += struct.pack("<I", 0)            # compression = none
    bmp_data += struct.pack("<I", len(raw_pixels))
    bmp_data += struct.pack("<i", 0)            # X pixels/meter
    bmp_data += struct.pack("<i", 0)            # Y pixels/meter
    bmp_data += struct.pack("<I", 0)            # colors used
    bmp_data += struct.pack("<I", 0)            # important colors

    # Pixel rows must be bottom-up for BMP
    row_bytes = [raw_pixels[r * SIZE * 4 : (r + 1) * SIZE * 4] for r in range(SIZE)]
    row_bytes.reverse()
    bmp_data += b"".join(row_bytes)

    # AND mask (all zeros = fully opaque) — SIZE rows * ceil(SIZE/32)*4 bytes wide
    mask_row_bytes = 4  # 32px wide / 8 bits = 4 bytes per row
    bmp_data += b"\x00" * (SIZE * mask_row_bytes)

    image_size = len(bmp_data)
    header_size = 6   # ICO file header
    entry_size  = 16  # one image directory entry
    image_offset = header_size + entry_size

    # ICO file header
    ico  = struct.pack("<HHH", 0, 1, 1)   # reserved, type=1(ICO), count=1

    # Image directory entry
    ico += struct.pack("BBBBHHII",
        SIZE,          # width
        SIZE,          # height
        0,             # color count (0 = more than 256)
        0,             # reserved
        1,             # color planes
        32,            # bits per pixel
        image_size,
        image_offset
    )

    ico += bmp_data
    ICON_FILE.write_bytes(ico)
    print(f"  [+] Icon created: {ICON_FILE}")


# ─── Step 2: Create the .lnk shortcut ────────────────────────────────────────

def make_shortcut_via_vbs():
    """Use a temporary VBScript to create the .lnk — works on all Windows."""
    icon_line = f'oShellLink.IconLocation = "{ICON_FILE},0"' if ICON_FILE.exists() else ""
    vbs = f"""
Set oWS = WScript.CreateObject("WScript.Shell")
Set oShellLink = oWS.CreateShortcut("{SHORTCUT}")
oShellLink.TargetPath = "{BAT_FILE}"
oShellLink.WorkingDirectory = "{ROOT}"
oShellLink.Description = "Antigravity TradeAI Hybrid Expert System"
oShellLink.WindowStyle = 1
{icon_line}
oShellLink.Save
"""
    vbs_path = ROOT / "_tmp_shortcut.vbs"
    vbs_path.write_text(vbs, encoding="utf-8")
    result = subprocess.run(["cscript", "//Nologo", str(vbs_path)],
                            capture_output=True, text=True)
    vbs_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)


def make_shortcut_via_win32():
    """Use win32com if available (usually present in Anaconda)."""
    import win32com.client  # type: ignore
    shell = win32com.client.Dispatch("WScript.Shell")
    lnk   = shell.CreateShortcut(str(SHORTCUT))
    lnk.TargetPath       = str(BAT_FILE)
    lnk.WorkingDirectory = str(ROOT)
    lnk.Description      = "Antigravity TradeAI Hybrid Expert System"
    lnk.WindowStyle      = 1
    if ICON_FILE.exists():
        lnk.IconLocation = f"{ICON_FILE},0"
    lnk.Save()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print()
    print("  ============================================================")
    print("   Antigravity TradeAI  -  Shortcut Installer")
    print("  ============================================================")
    print()

    if not BAT_FILE.exists():
        print(f"  [!] ERROR: TradeAI.bat not found at {BAT_FILE}")
        print("      Make sure this script is in the project root folder.")
        input("  Press Enter to exit...")
        sys.exit(1)

    # 1. Generate icon
    print("  [*] Generating icon...")
    try:
        make_icon()
    except Exception as e:
        print(f"  [!] Icon skipped: {e}")

    # 2. Create shortcut
    print("  [*] Creating Desktop shortcut...")
    try:
        make_shortcut_via_win32()
        print("  [+] Shortcut created (win32com method)")
    except Exception:
        try:
            make_shortcut_via_vbs()
            print("  [+] Shortcut created (VBScript method)")
        except Exception as e2:
            print(f"  [!] ERROR creating shortcut: {e2}")
            print("      You can still launch the app by double-clicking TradeAI.bat")
            input("  Press Enter to exit...")
            sys.exit(1)

    print()
    print("  ============================================================")
    print("   SUCCESS! Shortcut placed on your Desktop.")
    print()
    print("   Just double-click  'Antigravity TradeAI'  on your Desktop")
    print("   to launch the app anytime - no terminal needed!")
    print("  ============================================================")
    print()
    input("  Press Enter to close...")


if __name__ == "__main__":
    main()
