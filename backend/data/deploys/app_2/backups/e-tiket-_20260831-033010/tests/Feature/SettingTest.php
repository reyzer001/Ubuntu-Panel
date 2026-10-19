<?php

use App\Models\Setting;
use App\Models\Ticket;
use App\Models\User;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;

uses()->group('settings');

it('redirects guests away from the settings page', function () {
    $this->get(route('admin.settings.edit'))->assertRedirect(route('login'));
});

it('forbids non admins from changing the company logo', function () {
    $technician = User::factory()->technician()->create();

    $this->actingAs($technician)->get(route('admin.settings.edit'))->assertForbidden();

    $this->actingAs($technician)->post(route('admin.settings.update'), [
        'logo' => UploadedFile::fake()->image('logo.png'),
    ])->assertForbidden();
});

it('shows the settings form to admins', function () {
    $admin = User::factory()->admin()->create();

    $this->actingAs($admin)
        ->get(route('admin.settings.edit'))
        ->assertOk()
        ->assertSee('Logo Perusahaan')
        ->assertSee('Belum ada logo');
});

it('stores an uploaded logo and keeps it until replaced', function () {
    Storage::fake('public');
    $admin = User::factory()->admin()->create();
    $logo = UploadedFile::fake()->image('logo.png', 120, 120);

    $this->actingAs($admin)
        ->post(route('admin.settings.update'), ['logo' => $logo])
        ->assertRedirect(route('admin.settings.edit'))
        ->assertSessionHas('success');

    $stored = Setting::get(Setting::KEY_COMPANY_LOGO);

    expect($stored)->not->toBeNull()
        ->and(Storage::disk('public')->exists((string) $stored))->toBeTrue()
        ->and(Setting::companyLogoUrl())->toContain('storage/');

    // The logo stays active on later requests without uploading again.
    $this->actingAs($admin)
        ->get(route('dashboard'))
        ->assertOk()
        ->assertSee(Storage::disk('public')->url((string) $stored));
});

it('deletes the previous logo when a new one is uploaded', function () {
    Storage::fake('public');
    $admin = User::factory()->admin()->create();

    $this->actingAs($admin)->post(route('admin.settings.update'), [
        'logo' => UploadedFile::fake()->image('first.png'),
    ]);

    $firstPath = (string) Setting::get(Setting::KEY_COMPANY_LOGO);

    $this->actingAs($admin)->post(route('admin.settings.update'), [
        'logo' => UploadedFile::fake()->image('second.jpg'),
    ]);

    $secondPath = (string) Setting::get(Setting::KEY_COMPANY_LOGO);

    expect($secondPath)->not->toBe($firstPath)
        ->and(Storage::disk('public')->exists($firstPath))->toBeFalse()
        ->and(Storage::disk('public')->exists($secondPath))->toBeTrue();
});

it('rejects uploads that are not jpg or png images', function () {
    Storage::fake('public');
    $admin = User::factory()->admin()->create();

    $this->actingAs($admin)
        ->post(route('admin.settings.update'), [
            'logo' => UploadedFile::fake()->create('not-an-image.txt', 10),
        ])
        ->assertSessionHasErrors(['logo']);

    expect(Setting::get(Setting::KEY_COMPANY_LOGO))->toBeNull();
});

it('embeds the company logo into the exported workbook', function () {
    Storage::fake('public');
    $admin = User::factory()->admin()->create();
    Ticket::factory()->resolved()->create(['resolved_at' => now()]);

    $this->actingAs($admin)->post(route('admin.settings.update'), [
        'logo' => UploadedFile::fake()->image('logo.png', 100, 100),
    ]);

    $response = $this->actingAs($admin)->get(route('reports.excel', ['period' => 'daily']));

    $path = tempnam(sys_get_temp_dir(), 'export-test');
    file_put_contents($path, $response->getContent());

    $zip = new ZipArchive;

    expect($zip->open($path, ZipArchive::CHECKCONS))->toBeTrue()
        ->and($zip->locateName('xl/media/image1.png'))->not->toBeFalse()
        ->and($zip->getFromName('xl/drawings/drawing1.xml'))
        ->toContain('<xdr:pic>')
        ->toContain('r:embed="rId1"')
        ->and($zip->getFromName('xl/worksheets/_rels/sheet1.xml.rels'))
        ->toContain('../drawings/drawing1.xml')
        ->and($zip->getFromName('xl/worksheets/sheet1.xml'))
        ->toContain('<drawing r:id="rId1"/>')
        ->and($zip->getFromName('[Content_Types].xml'))
        ->toContain('Extension="png"');

    $zip->close();
    unlink($path);
});
