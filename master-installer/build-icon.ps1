$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force 'master-installer/build' | Out-Null
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class NativeIconMaster {
    [DllImport("user32.dll", SetLastError=true)]
    public static extern bool DestroyIcon(IntPtr hIcon);
}
"@
function Add-RoundedRect([System.Drawing.Drawing2D.GraphicsPath]$path,[float]$x,[float]$y,[float]$w,[float]$h,[float]$r) {
  $d = $r * 2
  $path.AddArc($x,$y,$d,$d,180,90)
  $path.AddArc($x+$w-$d,$y,$d,$d,270,90)
  $path.AddArc($x+$w-$d,$y+$h-$d,$d,$d,0,90)
  $path.AddArc($x,$y+$h-$d,$d,$d,90,90)
  $path.CloseFigure()
}
$bmp = New-Object System.Drawing.Bitmap 64,64
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.Clear([System.Drawing.Color]::Transparent)
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
Add-RoundedRect $path 2 2 60 60 14
$clip = New-Object System.Drawing.Region($path)
$g.Clip = $clip
$teal = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(18,145,160))
$navy = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(27,61,91))
$g.FillRectangle($teal,2,2,30,60)
$g.FillRectangle($navy,32,2,30,60)
$g.ResetClip()
$cardPath = New-Object System.Drawing.Drawing2D.GraphicsPath
Add-RoundedRect $cardPath 10 11 44 42 8
$card = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(250,252,251))
$g.FillPath($card,$cardPath)
$font = New-Object System.Drawing.Font('Segoe UI',18,[System.Drawing.FontStyle]::Bold,[System.Drawing.GraphicsUnit]::Pixel)
$brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(25,88,111))
$fmt = New-Object System.Drawing.StringFormat
$fmt.Alignment = [System.Drawing.StringAlignment]::Center
$fmt.LineAlignment = [System.Drawing.StringAlignment]::Center
$g.DrawString('DR',$font,$brush,[System.Drawing.RectangleF]::new(10,11,44,42),$fmt)
$h=$bmp.GetHicon()
$ico=[System.Drawing.Icon]::FromHandle($h)
$fs=[IO.File]::Create('master-installer/build/consultorio_icon.ico')
try { $ico.Save($fs) } finally { $fs.Dispose() }
$ico.Dispose(); [NativeIconMaster]::DestroyIcon($h) | Out-Null
$fmt.Dispose(); $brush.Dispose(); $font.Dispose(); $card.Dispose(); $cardPath.Dispose()
$teal.Dispose(); $navy.Dispose(); $clip.Dispose(); $path.Dispose(); $g.Dispose(); $bmp.Dispose()
