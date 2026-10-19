<?php

use App\Models\User;
use Database\Seeders\DatabaseSeeder;
use Illuminate\Support\Facades\Hash;

uses()->group('auth');

it('shows the login page to guests', function () {
    $this->get('/login')->assertOk();
});

it('redirects authenticated users away from login', function () {
    $this->actingAs(User::factory()->create())
        ->get('/login')
        ->assertRedirect(route('dashboard'));
});

it('logs in with valid credentials', function () {
    $user = User::factory()->admin()->create([
        'password' => Hash::make('rahasia123'),
    ]);

    $this->post(route('login.post'), [
        'email' => $user->email,
        'password' => 'rahasia123',
    ])->assertRedirect(route('dashboard'));

    $this->assertAuthenticatedAs($user);
});

it('gives every seeded user a different password', function () {
    $this->seed(DatabaseSeeder::class);

    $credentials = [
        'admin@rs.com' => 'admin-efarina-2026',
        'budi@rs.com' => 'budi-hardware-2026',
        'siti@rs.com' => 'siti-network-2026',
        'ani@rs.com' => 'ani-igd-2026',
        'iwan@rs.com' => 'iwan-farmasi-2026',
        'dewi@rs.com' => 'dewi-icu-2026',
    ];

    foreach ($credentials as $email => $password) {
        $user = User::where('email', $email)->sole();

        expect(Hash::check($password, $user->password))->toBeTrue();

        foreach ($credentials as $otherPassword) {
            if ($otherPassword !== $password) {
                expect(Hash::check($otherPassword, $user->password))->toBeFalse();
            }
        }
    }
});

it('rejects invalid credentials', function () {
    $user = User::factory()->create();

    $this->from('/login')
        ->post(route('login.post'), [
            'email' => $user->email,
            'password' => 'wrong-password',
        ])
        ->assertRedirect('/login')
        ->assertSessionHasErrors('email');

    $this->assertGuest();
});

it('does not expose quick login', function () {
    $user = User::factory()->divisionHead()->create();

    $this->get("/quick-login/{$user->id}")
        ->assertNotFound();

    $this->assertGuest();
});

it('logs out and invalidates the session', function () {
    $user = User::factory()->create();

    $this->actingAs($user)
        ->post(route('logout'))
        ->assertRedirect(route('login'));

    $this->assertGuest();
});
