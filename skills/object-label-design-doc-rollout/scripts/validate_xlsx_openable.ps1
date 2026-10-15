param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$ReportPath
)

$ErrorActionPreference = 'Stop'
$folder = [System.IO.Path]::GetFullPath($Path)
$files = @(Get-ChildItem -LiteralPath $folder -Filter '*.xlsx' -File | Sort-Object Name)
$results = @()
$excel = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $excel.AskToUpdateLinks = $false
    $excel.EnableEvents = $false
    $excel.AutomationSecurity = 3

    foreach ($file in $files) {
        $workbook = $null
        try {
            # CorruptLoad=0 is xlNormalLoad. Files that require repair must fail.
            $workbook = $excel.Workbooks.Open($file.FullName, 0, $true, 5, '', '', $true, 2, '', $false, $false, 0, $false, $true)
            $results += [pscustomobject]@{
                file = $file.Name
                status = 'opened'
                worksheets = $workbook.Worksheets.Count
            }
        }
        catch {
            $results += [pscustomobject]@{
                file = $file.Name
                status = 'failed'
                error = $_.Exception.Message
            }
        }
        finally {
            if ($null -ne $workbook) {
                $workbook.Close($false)
                [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($workbook)
            }
        }
    }
}
finally {
    if ($null -ne $excel) {
        $excel.Quit()
        [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($excel)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}

$summary = [pscustomobject]@{
    total = $files.Count
    opened = @($results | Where-Object status -eq 'opened').Count
    failed = @($results | Where-Object status -eq 'failed').Count
    results = $results
}

$json = $summary | ConvertTo-Json -Depth 5
if ($ReportPath) {
    $report = [System.IO.Path]::GetFullPath($ReportPath)
    [System.IO.File]::WriteAllText($report, $json, [System.Text.UTF8Encoding]::new($false))
}
$json
if ($summary.failed -gt 0) {
    exit 1
}
