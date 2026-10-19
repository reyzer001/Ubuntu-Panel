<?php

use App\Models\Ticket;
use App\Models\User;
use Carbon\Carbon;

uses()->group('reports');

it('scopes reports to the authenticated role', function () {
    $technician = User::factory()->technician()->create();
    $ownTicket = Ticket::factory()->closed()->create(['technician_id' => $technician->id]);
    $otherTicket = Ticket::factory()->closed()->create();

    $this->actingAs($technician)
        ->get(route('reports.index', ['period' => 'yearly']))
        ->assertOk()
        ->assertSee($ownTicket->ticket_number)
        ->assertDontSee($otherTicket->ticket_number);
});

it('shows all completed tickets to admins and filters custom dates', function () {
    $admin = User::factory()->admin()->create();
    $included = Ticket::factory()->closed()->create(['resolved_at' => Carbon::parse('2026-08-10 10:00')]);
    $excluded = Ticket::factory()->closed()->create(['resolved_at' => Carbon::parse('2026-08-20 10:00')]);

    $this->actingAs($admin)
        ->get(route('reports.index', [
            'period' => 'custom',
            'from' => '2026-08-01',
            'to' => '2026-08-15',
        ]))
        ->assertOk()
        ->assertSee($included->ticket_number)
        ->assertDontSee($excluded->ticket_number);
});

it('exports filtered reports as a valid xlsx workbook following both templates', function () {
    $admin = User::factory()->admin()->create();
    $ticket = Ticket::factory()->resolved()->create(['resolved_at' => now()]);
    $query = ['period' => 'daily'];

    $response = $this->actingAs($admin)
        ->get(route('reports.excel', $query))
        ->assertOk()
        ->assertHeader('content-type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        ->assertDownload('rekapan-pekerjaan-'.now()->format('Y-m-d').'-'.now()->format('Y-m-d').'.xlsx');

    $path = tempnam(sys_get_temp_dir(), 'export-test');
    file_put_contents($path, $response->getContent());

    $zip = new ZipArchive;

    expect($zip->open($path, ZipArchive::CHECKCONS))->toBeTrue()
        // Sheet 1 follows the single-report template column order
        ->and($zip->getFromName('xl/worksheets/sheet1.xml'))
        ->toContain($ticket->ticket_number)
        ->toContain('REKAPAN LAPORAN PEKERJAAN IT SUPPORT')
        ->toContain('No. Laporan')
        ->toContain('<t xml:space="preserve">Tanggal</t>')
        ->toContain('Unit/Ruangan')
        ->toContain('Petugas IT')
        ->toContain('Tindakan/Penyelesaian')
        ->toContain('Foto Sebelum')
        ->toContain('Foto Sesudah')
        ->toContain('Verifikasi')
        ->toContain('state="frozen"')
        ->toContain('<autoFilter ref="A6:O7"/>')
        // Sheets 2 and 3 follow the recap template
        ->and($zip->getFromName('xl/workbook.xml'))
        ->toContain('Rekapan Pekerjaan')
        ->toContain('Ringkasan')
        ->toContain('Rekap Kategori')
        ->and($zip->getFromName('xl/worksheets/sheet2.xml'))
        ->toContain('TOTAL LAPORAN')
        ->toContain('TINGKAT PENYELESAIAN')
        ->and($zip->getFromName('xl/worksheets/sheet3.xml'))
        ->toContain('Kategori')
        ->toContain('TOTAL');

    $zip->close();
    unlink($path);
});

it('produces structurally valid xml for every exported sheet', function () {
    $admin = User::factory()->admin()->create();
    Ticket::factory()->count(3)->closed()->create(['resolved_at' => now()]);

    $response = $this->actingAs($admin)->get(route('reports.excel', ['period' => 'daily']));

    $path = tempnam(sys_get_temp_dir(), 'export-test');
    file_put_contents($path, $response->getContent());

    $zip = new ZipArchive;
    $zip->open($path);

    libxml_use_internal_errors(true);

    foreach ([1, 2, 3] as $sheetNumber) {
        $sheet = simplexml_load_string($zip->getFromName("xl/worksheets/sheet{$sheetNumber}.xml"));

        expect($sheet)->not->toBeFalse();
    }

    expect(libxml_get_errors())->toBeEmpty();

    libxml_use_internal_errors(false);
    $zip->close();
    unlink($path);
});

it('never references a style index outside the stylesheet definitions', function () {
    $admin = User::factory()->admin()->create();
    Ticket::factory()->count(5)->resolved()->create(['resolved_at' => now()]);

    $response = $this->actingAs($admin)->get(route('reports.excel', ['period' => 'daily']));

    $path = tempnam(sys_get_temp_dir(), 'export-test');
    file_put_contents($path, $response->getContent());

    $zip = new ZipArchive;
    $zip->open($path);

    preg_match('/cellXfs count="(\d+)"/', (string) $zip->getFromName('xl/styles.xml'), $styleCount);

    $highestReferenced = 0;
    foreach ([1, 2, 3] as $sheetNumber) {
        preg_match_all('/ s="(\d+)"/', (string) $zip->getFromName("xl/worksheets/sheet{$sheetNumber}.xml"), $matches);
        foreach ($matches[1] as $value) {
            $highestReferenced = max($highestReferenced, (int) $value);
        }
    }

    expect((int) $styleCount[1])->toBeGreaterThan(0)
        ->and($highestReferenced)->toBeLessThan((int) $styleCount[1]);

    $zip->close();
    unlink($path);
});

it('escapes special characters in exported cell values', function () {
    $admin = User::factory()->admin()->create();
    Ticket::factory()->resolved()->create([
        'subject' => 'Printer & PC "rusak" <serius> banget',
        'resolved_at' => now(),
    ]);

    $response = $this->actingAs($admin)->get(route('reports.excel', ['period' => 'daily']));

    $path = tempnam(sys_get_temp_dir(), 'export-test');
    file_put_contents($path, $response->getContent());

    $zip = new ZipArchive;
    $zip->open($path);

    libxml_use_internal_errors(true);
    $sheet = simplexml_load_string($zip->getFromName('xl/worksheets/sheet1.xml'));
    $sheet->registerXPathNamespace('m', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main');
    $subjects = $sheet->xpath('//m:row[@r="7"]/m:c[@r="H7"]/m:is/m:t');

    expect($sheet)->not->toBeFalse()
        ->and((string) $subjects[0])
        ->toBe('Printer & PC "rusak" <serius> banget');

    libxml_use_internal_errors(false);
    $zip->close();
    unlink($path);
});

it('no longer offers pdf export', function () {
    $admin = User::factory()->admin()->create();

    $this->actingAs($admin)->get('/reports/pdf')->assertNotFound();
});

it('requires both dates for a custom report period', function () {
    $this->actingAs(User::factory()->admin()->create())
        ->get(route('reports.index', ['period' => 'custom']))
        ->assertSessionHasErrors(['from', 'to']);
});
it('redirects guests from reports to login', function () {
    $this->get(route('reports.index'))->assertRedirect(route('login'));
});
