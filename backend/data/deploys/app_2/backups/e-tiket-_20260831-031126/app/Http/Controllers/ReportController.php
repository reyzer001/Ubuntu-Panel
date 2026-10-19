<?php

namespace App\Http\Controllers;

use App\Models\Category;
use App\Models\Setting;
use App\Models\Ticket;
use App\Models\User;
use Carbon\Carbon;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Facades\Storage;
use Illuminate\View\View;
use ZipArchive;

class ReportController extends Controller
{
    /**
     * Column widths per sheet layout, in print order.
     */
    private const DETAIL_WIDTHS = [11, 17, 22, 18, 20, 20, 10, 34, 34, 30, 21, 30, 13, 13, 20];

    private const SUMMARY_WIDTHS = [30, 15];

    private const CATEGORY_WIDTHS = [28, 10, 10, 10, 10];

    /**
     * Maximum rendered size of the floating company logo, in pixels.
     */
    private const LOGO_MAX_WIDTH = 150;

    private const LOGO_MAX_HEIGHT = 80;

    public function index(Request $request): View
    {
        Gate::authorize('viewAny', Ticket::class);

        [$from, $to, $filters] = $this->dateRange($request);
        $tickets = $this->reportQuery($request->user(), $from, $to)->paginate(25)->withQueryString();

        return view('reports.index', compact('tickets', 'filters'));
    }

    public function excel(Request $request): Response
    {
        Gate::authorize('viewAny', Ticket::class);

        [$from, $to] = $this->dateRange($request);
        $user = $request->user();

        $tickets = $this->reportQuery($user, $from, $to)->get();
        $content = $this->makeXlsx([
            'Rekapan Pekerjaan' => ['widths' => self::DETAIL_WIDTHS, 'xml' => $this->detailSheet($tickets, $from, $to)],
            'Ringkasan' => ['widths' => self::SUMMARY_WIDTHS, 'xml' => $this->summarySheet($user, $from, $to)],
            'Rekap Kategori' => ['widths' => self::CATEGORY_WIDTHS, 'xml' => $this->categorySheet($user, $from, $to)],
        ], $this->companyLogoImage());

        return response($content, 200, [
            'Content-Type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition' => 'attachment; filename="rekapan-pekerjaan-'.$from->format('Y-m-d').'-'.$to->format('Y-m-d').'.xlsx"',
            'Content-Length' => (string) strlen($content),
        ]);
    }

    /**
     * Binary payload and dimensions of the uploaded company logo, or null.
     *
     * @return array{bytes: string, extension: string, cx: int, cy: int}|null
     */
    private function companyLogoImage(): ?array
    {
        $path = Setting::get(Setting::KEY_COMPANY_LOGO);

        if ($path === null || ! Storage::disk('public')->exists($path)) {
            return null;
        }

        $absolute = Storage::disk('public')->path($path);
        $dimensions = getimagesize($absolute);

        if ($dimensions === false) {
            return null;
        }

        [$width, $height] = $dimensions;
        $scale = min(self::LOGO_MAX_WIDTH / $width, self::LOGO_MAX_HEIGHT / $height, 1);

        return [
            'bytes' => (string) file_get_contents($absolute),
            'extension' => strtolower(pathinfo($path, PATHINFO_EXTENSION)),
            'cx' => (int) round($width * $scale * 9525),
            'cy' => (int) round($height * $scale * 9525),
        ];
    }

    /** @return array{0: Carbon, 1: Carbon, 2: array{period: string, from: string, to: string}} */
    private function dateRange(Request $request): array
    {
        $validated = $request->validate([
            'period' => ['nullable', 'in:daily,weekly,yearly,custom,monthly'],
            'from' => ['required_if:period,custom', 'nullable', 'date'],
            'to' => ['required_if:period,custom', 'nullable', 'date', 'after_or_equal:from'],
        ]);

        $period = $validated['period'] ?? 'monthly';

        $now = now();
        [$from, $to] = match ($period) {
            'daily' => [$now->copy()->startOfDay(), $now->copy()->endOfDay()],
            'weekly' => [$now->copy()->startOfWeek(), $now->copy()->endOfWeek()],
            'yearly' => [$now->copy()->startOfYear(), $now->copy()->endOfYear()],
            'custom' => [Carbon::parse($request->input('from'))->startOfDay(), Carbon::parse($request->input('to'))->endOfDay()],
            default => [$now->copy()->startOfMonth(), $now->copy()->endOfMonth()],
        };

        abort_if($from->gt($to), 422);

        return [$from, $to, ['period' => $period, 'from' => $from->toDateString(), 'to' => $to->toDateString()]];
    }

    /**
     * Completed-work rows for the selected period, scoped by role.
     */
    private function reportQuery(User $user, Carbon $from, Carbon $to): Builder
    {
        return $this->roleScope($user)
            ->with(['category', 'division', 'creator', 'technician', 'logs'])
            ->whereIn('status', [Ticket::STATUS_RESOLVED, Ticket::STATUS_CLOSED])
            ->whereBetween('resolved_at', [$from, $to])->latest('resolved_at');
    }

    /**
     * Base ticket query limited to what the role may see.
     */
    private function roleScope(User $user): Builder
    {
        $query = Ticket::query();

        if ($user->isTechnician()) {
            $query->where('technician_id', $user->id);
        } elseif ($user->isDivisionHead()) {
            $query->where('creator_id', $user->id);
        }

        return $query;
    }

    /**
     * Detail sheet following the single-report template: a letterhead
     * block (title, period, floating logo) above the agreed columns.
     *
     * @param  Collection<int, Ticket>  $tickets
     */
    private function detailSheet(Collection $tickets, Carbon $from, Carbon $to): string
    {
        $headers = [
            'No. Laporan', 'Tanggal', 'Unit/Ruangan', 'Pelapor', 'Petugas IT',
            'Kategori', 'Prioritas', 'Kendala', 'Tindakan/Penyelesaian', 'Hasil',
            'Status', 'Keterangan', 'Foto Sebelum', 'Foto Sesudah', 'Verifikasi',
        ];

        // Zero-based indexes of long-text columns that wrap inside the cell,
        // short columns rendered centered, and the verification column that
        // wraps while staying centered.
        $wrappedColumns = [7, 8, 9, 11];
        $centeredColumns = [0, 1, 6, 10, 12, 13];
        $wrappedCenteredColumns = [14];

        $rows = [];
        foreach ($tickets as $index => $ticket) {
            $zebra = $index % 2 === 1;
            $baseStyle = $zebra ? 2 : 0;

            $values = [
                $ticket->ticket_number,
                $ticket->created_at?->format('d-m-Y H:i') ?? '-',
                $ticket->division?->name ?? '-',
                $ticket->creator?->name ?? '-',
                $ticket->technician?->name ?? '-',
                $ticket->category?->name ?? '-',
                ucfirst($ticket->priority),
                $ticket->subject,
                $this->actionNote($ticket),
                $this->resultNote($ticket),
                $this->statusLabel($ticket),
                '-',
                '-',
                '-',
                $ticket->status === Ticket::STATUS_CLOSED ? 'Terkonfirmasi selesai' : 'Menunggu konfirmasi',
            ];

            $cells = [];
            foreach ($values as $columnIndex => $value) {
                // Style indices must stay within the stylesheet definitions.
                $style = match (true) {
                    in_array($columnIndex, $wrappedColumns, true) => $zebra ? 4 : 3,
                    in_array($columnIndex, $centeredColumns, true) => $zebra ? 8 : 7,
                    in_array($columnIndex, $wrappedCenteredColumns, true) => $zebra ? 11 : 10,
                    default => $baseStyle,
                };
                $cells[] = self::cell($value, style: $style);
            }

            $rows[] = $cells;
        }

        // Letterhead rows; the company logo floats beside them when set and a
        // green rule closes the block, mirroring the printed template.
        $columns = range('A', chr(ord('A') + count(self::DETAIL_WIDTHS) - 1));
        $preambleRows = [
            2 => ['C' => self::cell('REKAPAN LAPORAN PEKERJAAN IT SUPPORT', style: 5)],
            3 => ['C' => self::cell('RS Efarina Etaham Karawang | Periode: '.$from->format('d-m-Y').' s/d '.$to->format('d-m-Y'), style: 6)],
            4 => array_combine($columns, array_fill(0, count($columns), self::cell('', style: 9))),
        ];

        return $this->sheetXml(
            $headers,
            $rows,
            count(self::DETAIL_WIDTHS),
            freezeHeader: true,
            autoFilter: true,
            headerRow: 6,
            preambleRows: $preambleRows,
            merges: ['C2:O2', 'C3:O3', 'A4:O4'],
            landscapePrint: true,
        );
    }

    /**
     * Summary indicators mirroring the recap template's cards.
     */
    private function summarySheet(User $user, Carbon $from, Carbon $to): string
    {
        $base = $this->roleScope($user)->whereBetween('created_at', [$from, $to]);

        $total = (clone $base)->count();
        $selesai = (clone $base)->whereIn('status', [Ticket::STATUS_RESOLVED, Ticket::STATUS_CLOSED])->count();
        $proses = (clone $base)->whereIn('status', [Ticket::STATUS_OPEN, Ticket::STATUS_ASSIGNED, Ticket::STATUS_IN_PROGRESS])->count();
        $pending = (clone $base)->where('status', Ticket::STATUS_PENDING)->count();
        $rate = $total > 0 ? round($selesai / $total * 100).'%' : '0%';

        $headers = ['Indikator', 'Nilai'];
        $rows = [
            [self::cell('TOTAL LAPORAN'), self::numberCell($total, style: 7)],
            [self::cell('SELESAI'), self::numberCell($selesai, style: 7)],
            [self::cell('DALAM PROSES'), self::numberCell($proses, style: 7)],
            [self::cell('PENDING'), self::numberCell($pending, style: 7)],
            [self::cell('TINGKAT PENYELESAIAN'), self::cell($rate, style: 7)],
        ];

        return $this->sheetXml($headers, $rows, count(self::SUMMARY_WIDTHS));
    }

    /**
     * Category breakdown mirroring the recap template's "REKAP PER KATEGORI".
     */
    private function categorySheet(User $user, Carbon $from, Carbon $to): string
    {
        $base = $this->roleScope($user)->whereBetween('created_at', [$from, $to]);

        $rows = [];
        foreach (Category::orderBy('name')->get() as $category) {
            $scope = fn (): Builder => (clone $base)->where('category_id', $category->id);

            $rows[] = $this->categoryRow($category->name, $scope);
        }

        $rows[] = $this->categoryRow('TOTAL', fn (): Builder => clone $base, totalStyle: true);

        $headers = ['Kategori', 'Total', 'Selesai', 'Proses', 'Pending'];

        return $this->sheetXml($headers, $rows, count(self::CATEGORY_WIDTHS));
    }

    /**
     * @param  callable(): Builder  $scope
     * @return array<int, array{type: string, value: int|string, style: int}>
     */
    private function categoryRow(string $label, callable $scope, bool $totalStyle = false): array
    {
        $labelStyle = $totalStyle ? 1 : 0;
        $numberStyle = $totalStyle ? 1 : 7;

        return [
            self::cell($label, style: $labelStyle),
            self::numberCell($scope()->count(), style: $numberStyle),
            self::numberCell($scope()->whereIn('status', [Ticket::STATUS_RESOLVED, Ticket::STATUS_CLOSED])->count(), style: $numberStyle),
            self::numberCell($scope()->whereIn('status', [Ticket::STATUS_OPEN, Ticket::STATUS_ASSIGNED, Ticket::STATUS_IN_PROGRESS])->count(), style: $numberStyle),
            self::numberCell($scope()->where('status', Ticket::STATUS_PENDING)->count(), style: $numberStyle),
        ];
    }

    /** @return array{type: string, value: int|string, style: int} */
    private static function cell(int|string|null $value, int $style = 0): array
    {
        return ['type' => 'string', 'value' => $value ?? '-', 'style' => $style];
    }

    /** @return array{type: string, value: int|string, style: int} */
    private static function numberCell(int|string $value, int $style = 0): array
    {
        return ['type' => 'number', 'value' => $value, 'style' => $style];
    }

    private function actionNote(Ticket $ticket): string
    {
        return $ticket->logs->firstWhere('action', 'Mulai Penanganan')?->note ?? '-';
    }

    private function resultNote(Ticket $ticket): string
    {
        return $ticket->logs->firstWhere('action', 'Penyelesaian Masalah')?->note ?? '-';
    }

    private function statusLabel(Ticket $ticket): string
    {
        return match ($ticket->status) {
            Ticket::STATUS_CLOSED => 'SELESAI',
            Ticket::STATUS_RESOLVED => 'MENUNGGU KONFIRMASI',
            default => strtoupper(str_replace('_', ' ', $ticket->status)),
        };
    }

    /**
     * @param  array<int, string>  $headers
     * @param  array<int, array<int, array{type: string, value: int|string, style: int}>>  $rows
     * @param  array<int, array<string, array{type: string, value: int|string, style: int}>>  $preambleRows
     * @param  array<int, string>  $merges
     */
    private function sheetXml(array $headers, array $rows, int $columnCount, bool $freezeHeader = false, bool $autoFilter = false, int $headerRow = 1, array $preambleRows = [], array $merges = [], bool $landscapePrint = false): string
    {
        $columns = range('A', chr(ord('A') + $columnCount - 1));
        $headerCells = array_map(fn (string $header): array => self::cell($header, style: 1), $headers);

        $xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            .'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            .' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">';

        if ($landscapePrint) {
            $xml .= '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>';
        }

        if ($freezeHeader) {
            $xml .= '<sheetViews><sheetView workbookViewId="0">'
                .'<pane ySplit="'.$headerRow.'" topLeftCell="A'.($headerRow + 1).'" activePane="bottomLeft" state="frozen"/>'
                .'</sheetView></sheetViews>';
        }

        ksort($preambleRows);

        $xml .= '<sheetData>';

        foreach ($preambleRows as $rowNumber => $cells) {
            $xml .= $this->rowXml($rowNumber, $columns, $cells);
        }

        $xml .= $this->rowXml($headerRow, $columns, $headerCells, height: 24);

        foreach ($rows as $index => $cells) {
            $xml .= $this->rowXml($headerRow + 1 + $index, $columns, $cells);
        }

        $xml .= '</sheetData>';

        if ($autoFilter && $rows !== []) {
            $lastColumn = end($columns);
            $xml .= '<autoFilter ref="A'.$headerRow.':'.$lastColumn.($headerRow + count($rows)).'"/>';
        }

        if ($merges !== []) {
            $xml .= '<mergeCells count="'.count($merges).'">'
                .implode('', array_map(fn (string $range): string => '<mergeCell ref="'.$range.'"/>', $merges))
                .'</mergeCells>';
        }

        if ($landscapePrint) {
            $xml .= '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>'
                .'<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/>';
        }

        return $xml.'</worksheet>';
    }

    private function stylesXml(): string
    {
        return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            .'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            .'<fonts count="4">'
            .'<font><sz val="11"/><name val="Calibri"/></font>'
            .'<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
            .'<font><b/><sz val="14"/><color rgb="FF0F5132"/><name val="Calibri"/></font>'
            .'<font><sz val="10"/><color rgb="FF64748B"/><name val="Calibri"/></font>'
            .'</fonts>'
            .'<fills count="4">'
            .'<fill><patternFill patternType="none"/></fill>'
            .'<fill><patternFill patternType="gray125"/></fill>'
            .'<fill><patternFill patternType="solid"><fgColor rgb="FF047857"/><bgColor indexed="64"/></patternFill></fill>'
            .'<fill><patternFill patternType="solid"><fgColor rgb="FFF3F4F6"/><bgColor indexed="64"/></patternFill></fill>'
            .'</fills>'
            .'<borders count="3">'
            .'<border><left/><right/><top/><bottom/><diagonal/></border>'
            .'<border>'
            .'<left style="thin"><color rgb="FFCBD5E1"/></left>'
            .'<right style="thin"><color rgb="FFCBD5E1"/></right>'
            .'<top style="thin"><color rgb="FFCBD5E1"/></top>'
            .'<bottom style="thin"><color rgb="FFCBD5E1"/></bottom>'
            .'<diagonal/>'
            .'</border>'
            .'<border><left/><right/><top/><bottom style="medium"><color rgb="FF0F5132"/></bottom><diagonal/></border>'
            .'</borders>'
            .'<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            .'<cellXfs count="12">'
            .'<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>'
            .'<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
            .'<alignment vertical="center" horizontal="center" wrapText="1"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>'
            .'<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            .'<alignment vertical="top" wrapText="1"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">'
            .'<alignment vertical="top" wrapText="1"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
            .'<alignment vertical="center"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
            .'<alignment vertical="center"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            .'<alignment vertical="center" horizontal="center"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">'
            .'<alignment vertical="center" horizontal="center"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="0" fillId="0" borderId="2" xfId="0" applyBorder="1"/>'
            .'<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1">'
            .'<alignment vertical="top" horizontal="center" wrapText="1"/>'
            .'</xf>'
            .'<xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1" applyAlignment="1">'
            .'<alignment vertical="top" horizontal="center" wrapText="1"/>'
            .'</xf>'
            .'</cellXfs>'
            .'<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            .'</styleSheet>';
    }

    /**
     * @param  array<int, string>|array<string, array{type: string, value: int|string, style: int}>  $cells
     */
    private function rowXml(int $rowNumber, array $columns, array $cells, ?float $height = null): string
    {
        $xml = '<row r="'.$rowNumber.'"'.($height !== null ? ' ht="'.$height.'" customHeight="1"' : '').'>';

        if (array_is_list($cells)) {
            foreach (array_values($cells) as $index => $cell) {
                $xml .= $this->cellXml($columns[$index].$rowNumber, $cell);
            }

            return $xml.'</row>';
        }

        foreach ($cells as $column => $cell) {
            $xml .= $this->cellXml($column.$rowNumber, $cell);
        }

        return $xml.'</row>';
    }

    /**
     * @param  array{type: string, value: int|string, style: int}  $cell
     */
    private function cellXml(string $reference, array $cell): string
    {
        if ($cell['type'] === 'number') {
            return '<c r="'.$reference.'"'.($cell['style'] > 0 ? ' s="'.$cell['style'].'"' : '').'><v>'.$cell['value'].'</v></c>';
        }

        return '<c r="'.$reference.'" t="inlineStr"'.($cell['style'] > 0 ? ' s="'.$cell['style'].'"' : '').'>'
            .'<is><t xml:space="preserve">'.$this->escapeXml((string) $cell['value']).'</t></is></c>';
    }

    private function escapeXml(string $value): string
    {
        $clean = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F]/', '', $value) ?? '';

        return htmlspecialchars($clean, ENT_XML1 | ENT_QUOTES, 'UTF-8');
    }

    /**
     * Assemble a multi-sheet XLSX package, optionally embedding the
     * company logo as a floating picture on the first worksheet.
     *
     * @param  array<string, array{widths: array<int, int>, xml: string}>  $sheets
     * @param  array{bytes: string, extension: string, cx: int, cy: int}|null  $image
     * @param  int|null  $printTitleRow  worksheet row repeated atop every printed page of the first sheet
     */
    private function makeXlsx(array $sheets, ?array $image = null, ?int $printTitleRow = null): string
    {
        $names = array_keys($sheets);
        $overrides = '';
        $relationships = '';
        $workbookSheets = '';

        foreach ($names as $index => $name) {
            $position = $index + 1;

            $overrides .= '<Override PartName="/xl/worksheets/sheet'.$position.'.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
            $relationships .= '<Relationship Id="rId'.$position.'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet'.$position.'.xml"/>';
            $workbookSheets .= '<sheet name="'.$this->escapeXml($name).'" sheetId="'.$position.'" r:id="rId'.$position.'"/>';
        }

        if ($printTitleRow !== null) {
            $firstSheet = $this->escapeXml((string) $names[0]);
            $workbookSheets .= ''
                .'<definedNames>'
                .'<definedName name="_xlnm.Print_Titles" localSheetId="0">\''.$firstSheet.'\'!$'.$printTitleRow.':$'.$printTitleRow.'</definedName>'
                .'</definedNames>';
        }

        $stylesRelationshipId = 'rId'.(count($names) + 1);

        $contentTypes = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            .'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            .'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            .'<Default Extension="xml" ContentType="application/xml"/>';

        if ($image !== null) {
            $contentTypes .= '<Default Extension="'.strtolower($image['extension']).'" ContentType="image/'.($image['extension'] === 'jpg' ? 'jpeg' : $image['extension']).'"/>';
        }

        $contentTypes .= '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            .$overrides;

        if ($image !== null) {
            $contentTypes .= '<Override PartName="/xl/drawings/drawing1.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>';
        }

        $contentTypes .= '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            .'</Types>';

        $parts = [
            '[Content_Types].xml' => $contentTypes,
            '_rels/.rels' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                .'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                .'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                .'</Relationships>',
            'xl/workbook.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                .'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                .'<sheets>'.$workbookSheets.'</sheets>'
                .'</workbook>',
            'xl/_rels/workbook.xml.rels' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                .'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                .$relationships
                .'<Relationship Id="'.$stylesRelationshipId.'" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                .'</Relationships>',
            'xl/styles.xml' => $this->stylesXml(),
        ];

        foreach (array_values($sheets) as $sheetIndex => $config) {
            $parts['xl/worksheets/sheet'.($sheetIndex + 1).'.xml'] = $this->withColumns($config['xml'], $config['widths']);
        }

        if ($image !== null) {
            $mediaName = 'image1.'.strtolower($image['extension']);
            $parts['xl/media/'.$mediaName] = $image['bytes'];
            $parts['xl/drawings/drawing1.xml'] = $this->drawingXml($image['cx'], $image['cy']);
            $parts['xl/drawings/_rels/drawing1.xml.rels'] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                .'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                .'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/'.$mediaName.'"/>'
                .'</Relationships>';
            $parts['xl/worksheets/_rels/sheet1.xml.rels'] = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                .'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                .'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing" Target="../drawings/drawing1.xml"/>'
                .'</Relationships>';

            $firstSheet = 'xl/worksheets/sheet1.xml';
            $parts[$firstSheet] = str_replace('</worksheet>', '<drawing r:id="rId1"/></worksheet>', (string) $parts[$firstSheet]);
        }

        return $this->zipParts($parts);
    }

    /**
     * Floating one-cell anchor holding the company logo at A1.
     */
    private function drawingXml(int $cx, int $cy): string
    {
        return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            .'<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"'
            .' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            .'<xdr:oneCellAnchor>'
            .'<xdr:from><xdr:col>0</xdr:col><xdr:colOff>38100</xdr:colOff><xdr:row>0</xdr:row><xdr:rowOff>38100</xdr:rowOff></xdr:from>'
            .'<xdr:ext cx="'.$cx.'" cy="'.$cy.'"/>'
            .'<xdr:pic>'
            .'<xdr:nvPicPr><xdr:cNvPr id="1" name="Logo Perusahaan"/><xdr:cNvPicPr/></xdr:nvPicPr>'
            .'<xdr:blipFill><a:blip xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
            .'<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="'.$cx.'" cy="'.$cy.'"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr>'
            .'</xdr:pic>'
            .'<xdr:clientData/>'
            .'</xdr:oneCellAnchor>'
            .'</xdr:wsDr>';
    }

    /**
     * Inject the <cols> definition into a worksheet right before its sheetData.
     *
     * @param  array<int, int>  $widths
     */
    private function withColumns(string $sheetXml, array $widths): string
    {
        $cols = '<cols>';
        foreach (array_values($widths) as $index => $width) {
            $position = $index + 1;
            $cols .= '<col min="'.$position.'" max="'.$position.'" width="'.$width.'" customWidth="1"/>';
        }
        $cols .= '</cols>';

        return str_replace('<sheetData>', $cols.'<sheetData>', $sheetXml);
    }

    /**
     * @param  array<string, string>  $parts
     */
    private function zipParts(array $parts): string
    {
        $path = tempnam(sys_get_temp_dir(), 'xlsx');
        $zip = new ZipArchive;
        $zip->open($path, ZipArchive::OVERWRITE);

        foreach ($parts as $name => $contents) {
            $zip->addFromString($name, $contents);
        }

        $zip->close();
        $content = (string) file_get_contents($path);
        unlink($path);

        return $content;
    }
}
