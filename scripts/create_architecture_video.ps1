param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\outputs')
)

$ErrorActionPreference = 'Stop'

function Rgb([int]$r, [int]$g, [int]$b) {
    return $r + ($g * 256) + ($b * 65536)
}

$ink = Rgb 42 25 46
$muted = Rgb 105 91 111
$paper = Rgb 246 240 249
$paperRaised = Rgb 255 252 255
$lavender = Rgb 224 211 235
$accent = Rgb 145 103 161
$purple = Rgb 83 52 93
$green = Rgb 62 151 111
$amber = Rgb 215 148 31
$red = Rgb 195 72 82
$white = Rgb 255 255 255

$ppLayoutBlank = 12
$msoTextOrientationHorizontal = 1
$msoShapeRectangle = 1
$msoShapeRoundedRectangle = 5
$msoShapeOval = 9
$msoShapeChevron = 52
$msoFalse = 0
$msoTrue = -1
$ppAlignCenter = 2
$ppAlignLeft = 1
$ppSaveAsOpenXMLPresentation = 24

function Add-Text($slide, [string]$text, [float]$x, [float]$y, [float]$w, [float]$h,
                  [float]$size = 24, [int]$color = $ink, [bool]$bold = $false,
                  [int]$align = $ppAlignLeft) {
    $shape = $slide.Shapes.AddTextbox($msoTextOrientationHorizontal, $x, $y, $w, $h)
    $shape.TextFrame.TextRange.Text = $text
    $shape.TextFrame.TextRange.Font.Name = 'Aptos'
    $shape.TextFrame.TextRange.Font.Size = $size
    $shape.TextFrame.TextRange.Font.Color.RGB = $color
    $shape.TextFrame.TextRange.Font.Bold = if ($bold) { $msoTrue } else { $msoFalse }
    $shape.TextFrame.TextRange.ParagraphFormat.Alignment = $align
    $shape.TextFrame.MarginLeft = 4
    $shape.TextFrame.MarginRight = 4
    $shape.TextFrame.MarginTop = 2
    $shape.TextFrame.MarginBottom = 2
    return $shape
}

function Add-Box($slide, [string]$title, [string]$body, [float]$x, [float]$y,
                 [float]$w, [float]$h, [int]$fill = $paperRaised, [int]$line = $lavender,
                 [int]$titleColor = $purple) {
    $box = $slide.Shapes.AddShape($msoShapeRoundedRectangle, $x, $y, $w, $h)
    $box.Fill.ForeColor.RGB = $fill
    $box.Line.ForeColor.RGB = $line
    $box.Line.Weight = 1.2
    [void](Add-Text $slide $title ($x + 13) ($y + 10) ($w - 26) 27 16 $titleColor $true)
    [void](Add-Text $slide $body ($x + 13) ($y + 39) ($w - 26) ($h - 48) 10.5 $muted $false)
    return $box
}

function Add-Arrow($slide, [float]$x, [float]$y, [float]$w, [float]$h, [int]$color = $accent) {
    $arrow = $slide.Shapes.AddShape($msoShapeChevron, $x, $y, $w, $h)
    $arrow.Fill.ForeColor.RGB = $color
    $arrow.Line.Visible = $msoFalse
    return $arrow
}

function New-BaseSlide($presentation, [string]$kicker, [string]$title, [string]$subtitle, [int]$number) {
    $slide = $presentation.Slides.Add($presentation.Slides.Count + 1, $ppLayoutBlank)
    $bg = $slide.Shapes.AddShape($msoShapeRectangle, 0, 0, 960, 540)
    $bg.Fill.ForeColor.RGB = $paper
    $bg.Line.Visible = $msoFalse
    [void](Add-Text $slide $kicker 42 25 690 22 10 $accent $true)
    [void](Add-Text $slide $title 42 49 850 53 30 $ink $true)
    [void](Add-Text $slide $subtitle 44 103 840 40 12 $muted $false)
    [void](Add-Text $slide ("{0:D2} / 08" -f $number) 845 29 70 20 9 $muted $false $ppAlignCenter)
    return $slide
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$pptxPath = Join-Path $OutputDirectory 'medtrust-architecture-explainer.pptx'
$videoPath = Join-Path $OutputDirectory 'medtrust-architecture-explainer.mp4'

$powerPoint = New-Object -ComObject PowerPoint.Application
$powerPoint.Visible = $msoTrue
$presentation = $powerPoint.Presentations.Add()
$presentation.PageSetup.SlideWidth = 960
$presentation.PageSetup.SlideHeight = 540

try {
    # 1 — Opening
    $s = New-BaseSlide $presentation 'MEDTRUST CONNECT' 'How the medication-safety prototype works' 'Architecture, data flow, security boundaries, and practical use — explained from the current codebase.' 1
    $circle = $s.Shapes.AddShape($msoShapeOval, 353, 175, 254, 254)
    $circle.Fill.ForeColor.RGB = $lavender
    $circle.Line.ForeColor.RGB = $accent
    $circle.Line.Weight = 2
    [void](Add-Text $s 'MEDTRUST' 373 253 214 38 26 $purple $true $ppAlignCenter)
    [void](Add-Text $s 'CONNECT' 388 292 184 28 14 $accent $true $ppAlignCenter)
    [void](Add-Text $s 'A deterministic rule engine decides findings. AI explains; it does not decide severity.' 210 458 540 42 13 $ink $false $ppAlignCenter)

    # 2 — System map
    $s = New-BaseSlide $presentation '01 · SYSTEM MAP' 'Two experiences, one controlled backend' 'Patients and clinical staff use different interfaces, while Flask applies one shared authentication, authorization, and audit boundary.' 2
    [void](Add-Box $s 'Patient web app' 'Quick check\nPatient login\nPrescription status' 42 190 190 145 $paperRaised $lavender)
    [void](Add-Arrow $s 247 237 55 36)
    [void](Add-Box $s 'Flask API boundary' 'JWT + roles\nTenant isolation\nRate limits\nInput validation' 317 176 200 172 $purple $purple $white)
    [void](Add-Arrow $s 532 237 55 36)
    [void](Add-Box $s 'Clinical console' 'Pharmacist review\nPrescriber response\nRule governance' 602 190 190 145 $paperRaised $lavender)
    [void](Add-Text $s 'The same API also coordinates the database, evidence retrieval, and explanation service.' 178 407 604 40 13 $muted $false $ppAlignCenter)

    # 3 — Guest flow
    $s = New-BaseSlide $presentation '02 · PATIENT DATA FLOW' 'From typed medications to a transparent result' 'A guest check is designed to be deterministic and not saved as a patient record.' 3
    $labels = @(
        @('1 · Enter', 'Medication, current drugs, allergies'),
        @('2 · Normalize', 'Resolve names and ingredients'),
        @('3 · Evaluate', 'Approved DDI, allergy, duplicate rules'),
        @('4 · Explain', 'Plain language + evidence citations'),
        @('5 · Display', 'Severity, coverage, unresolved gaps')
    )
    for ($i = 0; $i -lt $labels.Count; $i++) {
        $x = 31 + ($i * 183)
        [void](Add-Box $s $labels[$i][0] $labels[$i][1] $x 205 155 120 $paperRaised $lavender)
        if ($i -lt 4) { [void](Add-Arrow $s ($x + 158) 245 22 28) }
    }
    [void](Add-Text $s 'Important: “no finding” means no stored rule matched — never proof that a combination is safe.' 147 391 666 46 14 $red $true $ppAlignCenter)

    # 4 — Rule engine
    $s = New-BaseSlide $presentation '03 · DECISION ENGINE' 'Rules make the finding; AI only explains it' 'The medical decision path is intentionally separated from generated language.' 4
    [void](Add-Box $s 'Approved interaction rule' 'Exact ingredient pair\nStored severity\nClinical effect\nSource and version' 60 190 220 176 $paperRaised $lavender)
    [void](Add-Arrow $s 298 253 56 36)
    [void](Add-Box $s 'Deterministic finding' 'Critical · Major\nCaution · Informational\nUnknown / manual review' 372 190 220 176 $purple $purple $white)
    [void](Add-Arrow $s 610 253 56 36)
    [void](Add-Box $s 'Constrained explanation' 'Receives an existing finding\nUses evidence excerpts\nCannot change severity' 684 190 220 176 $paperRaised $lavender)
    [void](Add-Text $s 'Also implemented: exact allergy matching and duplicate-ingredient detection.' 178 417 604 33 13 $green $true $ppAlignCenter)

    # 5 — Clinical workflow
    $s = New-BaseSlide $presentation '04 · CLINICAL WORKFLOW' 'A professional remains responsible for action' 'The console supports review and communication; it does not autonomously prescribe or dispense.' 5
    $steps = @(
        @('Prescription', 'Case created'),
        @('Analysis', 'Findings generated'),
        @('Pharmacist', 'Approve or escalate'),
        @('Prescriber', 'Respond if needed'),
        @('Patient', 'Reviewed message'),
        @('Outcome', 'Dispense, hold, close')
    )
    for ($i = 0; $i -lt $steps.Count; $i++) {
        $x = 30 + (($i % 3) * 300)
        $y = 176 + ([math]::Floor($i / 3) * 155)
        [void](Add-Box $s $steps[$i][0] $steps[$i][1] $x $y 230 92 $paperRaised $lavender)
        if (($i % 3) -lt 2) { [void](Add-Arrow $s ($x + 242) ($y + 31) 39 28) }
    }
    [void](Add-Text $s 'Every meaningful state change is intended to create an append-only audit event.' 187 463 586 30 12 $purple $true $ppAlignCenter)

    # 6 — Storage/evidence
    $s = New-BaseSlide $presentation '05 · DATA LAYERS' 'Operational records and evidence are kept distinct' 'The database supports workflow history, approved rules, versioned evidence chunks, and auditability.' 6
    [void](Add-Box $s 'Operational records' 'Organizations\nUsers and roles\nPatients and prescriptions\nSafety cases and findings' 46 185 250 190 $paperRaised $lavender)
    [void](Add-Box $s 'Clinical knowledge' 'Candidate and approved rules\nSource dataset\nReviewer + timestamp\nRule version' 355 185 250 190 $paperRaised $lavender)
    [void](Add-Box $s 'Evidence store' 'FDA-label chunks\nEmbeddings\nDataset + chunk version\nModel + ingestion time' 664 185 250 190 $paperRaised $lavender)
    [void](Add-Text $s 'Cohere creates embeddings. Groq creates constrained explanations. Neither replaces rule approval.' 149 421 662 42 13 $ink $true $ppAlignCenter)

    # 7 — Security
    $s = New-BaseSlide $presentation '06 · SECURITY BOUNDARY' 'What every protected request must pass' 'The current Flask boundary provides useful prototype controls, but it is not yet a hospital-grade API gateway.' 7
    $checks = @(
        @('JWT', 'Signed token\n24-hour expiry'),
        @('Role', 'Patient vs clinical\nprivileges'),
        @('Tenant', 'Same organization\n404 across boundaries'),
        @('Limits', 'Per-IP throttling\nInput length caps'),
        @('Audit', 'Login + clinical\nworkflow events'),
        @('Safety', 'Prototype gate\nFeature kill switches')
    )
    for ($i = 0; $i -lt $checks.Count; $i++) {
        $x = 37 + (($i % 3) * 305)
        $y = 173 + ([math]::Floor($i / 3) * 137)
        [void](Add-Box $s $checks[$i][0] $checks[$i][1] $x $y 255 100 $paperRaised $lavender)
    }
    [void](Add-Text $s 'Before hospital use: MFA, revocation, persistent rate limits, WAF, security headers, pen testing, and formal privacy controls.' 102 449 756 43 12 $red $true $ppAlignCenter)

    # 8 — Uses and boundary
    $s = New-BaseSlide $presentation '07 · PRACTICAL USE' 'Where this prototype creates value today' 'The strongest use is a transparent demonstration of workflow and safety engineering—not an independently validated clinical product.' 8
    [void](Add-Box $s 'Patient education' 'Prepare clearer questions\nUnderstand why review matters' 58 184 245 145 $paperRaised $lavender)
    [void](Add-Box $s 'Clinical workflow demo' 'Show review queues\nGovern rules and decisions' 357 184 245 145 $paperRaised $lavender)
    [void](Add-Box $s 'Hospital design partnership' 'Retrospective validation\nWorkflow feedback\nData-use agreement' 656 184 245 145 $paperRaised $lavender)
    [void](Add-Text $s 'Next milestone' 330 381 300 26 12 $accent $true $ppAlignCenter)
    [void](Add-Text $s 'Validate the knowledge base and workflow with licensed clinicians before real patient care.' 158 412 644 51 17 $purple $true $ppAlignCenter)

    $presentation.SaveAs($pptxPath, $ppSaveAsOpenXMLPresentation)
    if (Test-Path -LiteralPath $videoPath) { Remove-Item -LiteralPath $videoPath -Force }

    # Use fixed slide timing so the exported video is deterministic and does
    # not depend on PowerPoint narration settings on the host machine.
    $presentation.CreateVideo($videoPath, $false, 6, 1080, 30, 85)
    $deadline = (Get-Date).AddMinutes(12)
    while ($presentation.CreateVideoStatus -in @(1, 2)) {
        if ((Get-Date) -gt $deadline) { throw 'PowerPoint video export timed out.' }
        Start-Sleep -Seconds 2
    }
    if ($presentation.CreateVideoStatus -ne 3 -or -not (Test-Path -LiteralPath $videoPath)) {
        throw "PowerPoint video export failed with status $($presentation.CreateVideoStatus)."
    }

    Write-Output "PPTX=$pptxPath"
    Write-Output "MP4=$videoPath"
    Write-Output "MP4_BYTES=$((Get-Item -LiteralPath $videoPath).Length)"
}
finally {
    if ($presentation) { $presentation.Close() }
    if ($powerPoint) { $powerPoint.Quit() }
    if ($presentation) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) }
    if ($powerPoint) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint) }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
