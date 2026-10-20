# Builds controlled Word / Excel / PowerPoint reference documents with the real Office applications (COM).
# Content: headings, paragraphs, a table, a picture, Japanese and mixed-language text, a landscape page / slide size.
# Developer QA harness (not shipped). Usage: powershell -File make_office_refs.ps1 -Out <folder>
param([Parameter(Mandatory)][string]$Out)
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
Add-Type -AssemblyName System.Drawing
$jp = [string]::Join("", @([char]0x65E5, [char]0x672C, [char]0x8A9E, [char]0x306E, [char]0x30C6, [char]0x30AD, [char]0x30B9, [char]0x30C8))   # 日本語のテキスト
$mix = "Order 2026-17 " + [string]::Join("", @([char]0x6CE8, [char]0x6587, [char]0x756A, [char]0x53F7)) + " Hello"                          # Order 2026-17 注文番号 Hello
# a plain picture: blue rectangle with a red square
$png = Join-Path $Out "picture.png"
$bmp = New-Object System.Drawing.Bitmap 240, 120; $g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::FromArgb(30, 90, 200)); $g.FillRectangle([System.Drawing.Brushes]::Red, 20, 20, 60, 60); $g.Dispose(); $bmp.Save($png); $bmp.Dispose()

# ---------------- Word: 2 pages, second page landscape
$w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0
try {
    $d = $w.Documents.Add()
    function EndRange($doc) { $doc.Range($doc.Content.End - 1, $doc.Content.End - 1) }
    (EndRange $d).InsertAfter("Quarterly Report Heading`r")
    $d.Paragraphs.Item(1).Style = "Heading 1"
    (EndRange $d).InsertAfter("Body paragraph one with ordinary words for the reference check.`r")
    (EndRange $d).InsertAfter($jp + "`r")
    (EndRange $d).InsertAfter($mix + "`r")
    $t = $d.Tables.Add((EndRange $d), 3, 3); $t.Borders.Enable = $true
    $cells = @(@("Item", "Qty", "Price"), @("Apple", "12", "1.25"), @("Pear", "7", "0.80"))
    for ($r = 1; $r -le 3; $r++) { for ($c = 1; $c -le 3; $c++) { $t.Cell($r, $c).Range.Text = $cells[$r - 1][$c - 1] } }
    (EndRange $d).InsertAfter("`r")
    [void]$d.InlineShapes.AddPicture($png, $false, $true, (EndRange $d))
    (EndRange $d).InsertAfter("`r")
    (EndRange $d).InsertBreak(7)
    (EndRange $d).InsertAfter("Second page in landscape orientation.")
    $d.Sections.Item(1).PageSetup.Orientation = 0
    [void]$d.Sections.Add((EndRange $d), 2)
    $d.Sections.Item($d.Sections.Count).PageSetup.Orientation = 1
    (EndRange $d).InsertAfter("Landscape section text.")
    "word pages: " + $d.ComputeStatistics(2)
    $d.SaveAs2([ref](Join-Path $Out "ref.docx"), [ref]12); $d.Close($false)
} finally { $w.Quit() }

# ---------------- Excel: table with numbers and Japanese, landscape
$x = New-Object -ComObject Excel.Application; $x.Visible = $false; $x.DisplayAlerts = $false
try {
    $wb = $x.Workbooks.Add(); $ws = $wb.Worksheets.Item(1)
    $ws.Range("A1").Value2 = "Item"; $ws.Range("B1").Value2 = "Qty"; $ws.Range("C1").Value2 = "Price"; $ws.Range("D1").Value2 = $jp
    $ws.Range("A2").Value2 = "Apple"; $ws.Range("B2").Value2 = 12; $ws.Range("C2").Value2 = 1.25; $ws.Range("D2").Value2 = $mix
    $ws.Range("A3").Value2 = "Pear"; $ws.Range("B3").Value2 = 7; $ws.Range("C3").Value2 = 0.8
    $ws.Range("A1:D3").Borders.LineStyle = 1
    $ws.PageSetup.Orientation = 2
    $wb.SaveAs((Join-Path $Out "ref.xlsx"), 51); $wb.Close($false)
} finally { $x.Quit() }

# ---------------- PowerPoint: 3 slides, 16:9, title, table, picture, Japanese
$p = New-Object -ComObject PowerPoint.Application
try {
    $pres = $p.Presentations.Add(0)
    $s1 = $pres.Slides.Add(1, 12); $tb = $s1.Shapes.AddTextbox(1, 40, 40, 600, 60); $tb.TextFrame.TextRange.Text = "Slide One Title"; $tb.TextFrame.TextRange.Font.Size = 36
    $tb2 = $s1.Shapes.AddTextbox(1, 40, 140, 600, 60); $tb2.TextFrame.TextRange.Text = $jp + " / " + $mix
    $s2 = $pres.Slides.Add(2, 12); $tbl = $s2.Shapes.AddTable(3, 3, 40, 60, 500, 150).Table
    for ($r = 1; $r -le 3; $r++) { for ($c = 1; $c -le 3; $c++) { $tbl.Cell($r, $c).Shape.TextFrame.TextRange.Text = $cells[$r - 1][$c - 1] } }
    $s3 = $pres.Slides.Add(3, 12); [void]$s3.Shapes.AddPicture($png, 0, -1, 60, 60, 240, 120)
    $pres.SaveAs((Join-Path $Out "ref.pptx")); $pres.Close()
    "pptx slide size: " + $pres.PageSetup.SlideWidth
} catch { "pptx error: " + $_.Exception.Message } finally { $p.Quit() }
Get-ChildItem $Out | Select-Object Name, Length
