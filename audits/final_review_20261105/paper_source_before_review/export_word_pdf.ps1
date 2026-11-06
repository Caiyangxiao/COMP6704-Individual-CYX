param(
    [string]$DocumentPath = (Join-Path $PSScriptRoot '..\submission\Yangxiao Cai+26023041r.docx'),
    [string]$PdfPath = (Join-Path $PSScriptRoot '..\submission\_word_pages.pdf')
)
$ErrorActionPreference = 'Stop'
$wordApp = $null
$reportDocument = $null
try {
    $DocumentPath = [System.IO.Path]::GetFullPath($DocumentPath)
    $PdfPath = [System.IO.Path]::GetFullPath($PdfPath)
    $wordApp = New-Object -ComObject Word.Application
    $wordApp.Visible = $false
    $wordApp.DisplayAlerts = 0
    $reportDocument = $wordApp.Documents.Open($DocumentPath, $false, $true, $false)
    $reportDocument.Repaginate()
    $pageCount = $reportDocument.ComputeStatistics(2)
    $reportDocument.ExportAsFixedFormat($PdfPath, 17)
    Write-Output ('Native Word page count: ' + $pageCount)
    Write-Output ('Exported: ' + $PdfPath)
}
finally {
    if ($null -ne $reportDocument) { $reportDocument.Close(0) }
    if ($null -ne $wordApp) { $wordApp.Quit() }
}
