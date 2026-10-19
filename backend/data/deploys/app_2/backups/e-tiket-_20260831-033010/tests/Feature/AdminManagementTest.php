<?php

use App\Models\Category;
use App\Models\Division;
use App\Models\Ticket;
use App\Models\User;
use Illuminate\Support\Facades\Hash;

uses()->group('admin');

it('forbids non admins from admin pages', function () {
    foreach ([User::factory()->technician(), User::factory()->divisionHead()] as $user) {
        $this->actingAs($user->create())
            ->get(route('admin.users.index'))
            ->assertForbidden();
    }
});

it('lists users for admins', function () {
    $user = User::factory()->create();

    $this->actingAs(User::factory()->admin()->create())
        ->get(route('admin.users.index'))
        ->assertOk()
        ->assertSee($user->name);
});

it('stores a new user', function () {
    $division = Division::factory()->create();

    $this->actingAs(User::factory()->admin()->create())
        ->post(route('admin.users.store'), [
            'name' => 'Teknisi Baru',
            'email' => 'teknisi.baru@rs.com',
            'password' => 'rahasia123',
            'role' => User::ROLE_TECHNICIAN,
            'phone' => '081234567890',
        ])
        ->assertRedirect(route('admin.users.index'))
        ->assertSessionHas('success');

    $user = User::where('email', 'teknisi.baru@rs.com')->sole();

    expect(Hash::check('rahasia123', $user->password))->toBeTrue()
        ->and($user->role)->toBe(User::ROLE_TECHNICIAN)
        ->and($user->is_active)->toBeTrue()
        ->and($user->division_id)->toBeNull();
});

it('requires a division when storing a division head', function () {
    $this->actingAs(User::factory()->admin()->create())
        ->post(route('admin.users.store'), [
            'name' => 'Ka Divisi Tanpa Divisi',
            'email' => 'kadiv@rs.com',
            'password' => 'rahasia123',
            'role' => User::ROLE_DIVISION_HEAD,
        ])
        ->assertSessionHasErrors('division_id');

    expect(User::where('email', 'kadiv@rs.com')->exists())->toBeFalse();
});

it('updates a user without changing password', function () {
    $target = User::factory()->technician()->create();
    $oldHash = $target->password;

    $this->actingAs(User::factory()->admin()->create())
        ->put(route('admin.users.update', $target), [
            'name' => 'Nama Baru',
            'email' => $target->email,
            'password' => '',
            'role' => User::ROLE_TECHNICIAN,
            'phone' => '089900011122',
        ])
        ->assertRedirect(route('admin.users.index'))
        ->assertSessionHas('success');

    expect($target->fresh()->name)->toBe('Nama Baru')
        ->and($target->fresh()->password)->toBe($oldHash)
        ->and($target->fresh()->phone)->toBe('089900011122');
});

it('toggles user status but protects the current account', function () {
    $admin = User::factory()->admin()->create();
    $target = User::factory()->technician()->create();

    $this->actingAs($admin)->patch(route('admin.users.toggle', $target));
    expect($target->fresh()->is_active)->toBeFalse();

    $this->patch(route('admin.users.toggle', $admin))
        ->assertSessionHas('error');
    expect($admin->fresh()->is_active)->toBeTrue();
});

it('deletes users without ticket history', function () {
    $admin = User::factory()->admin()->create();
    $target = User::factory()->technician()->create();

    $this->actingAs($admin)
        ->delete(route('admin.users.destroy', $target))
        ->assertRedirect(route('admin.users.index'))
        ->assertSessionHas('success');

    expect(User::find($target->id))->toBeNull();
});

it('deletes users with their created ticket history and protects the current account', function () {
    $admin = User::factory()->admin()->create();
    $target = User::factory()->divisionHead()->create();
    $ticket = Ticket::factory()->create(['creator_id' => $target->id, 'division_id' => $target->division_id]);

    $this->actingAs($admin)
        ->delete(route('admin.users.destroy', $target))
        ->assertRedirect(route('admin.users.index'))
        ->assertSessionHas('success');

    expect(User::find($target->id))->toBeNull()
        ->and(Ticket::find($ticket->id))->toBeNull();

    $this->delete(route('admin.users.destroy', $admin))
        ->assertRedirect()
        ->assertSessionHas('error');

    expect(User::find($admin->id))->not->toBeNull();
});

it('manages categories with sla values', function () {
    $admin = User::factory()->admin()->create();

    // Create
    $this->actingAs($admin)
        ->post(route('admin.categories.store'), [
            'name' => 'Jaringan & Internet',
            'sla_response_minutes' => 30,
            'sla_resolve_minutes' => 120,
        ])
        ->assertRedirect(route('admin.categories.index'))
        ->assertSessionHas('success');

    $category = Category::where('name', 'Jaringan & Internet')->sole();
    expect($category->sla_resolve_minutes)->toBe(120);

    // Duplicate name is rejected
    $this->post(route('admin.categories.store'), [
        'name' => 'Jaringan & Internet',
        'sla_response_minutes' => 30,
        'sla_resolve_minutes' => 120,
    ])->assertSessionHasErrors('name');

    // Update
    $this->put(route('admin.categories.update', $category), [
        'name' => 'Jaringan',
        'sla_response_minutes' => 15,
        'sla_resolve_minutes' => 60,
    ])->assertSessionHas('success');

    expect($category->fresh()->name)->toBe('Jaringan')
        ->and($category->fresh()->sla_response_minutes)->toBe(15);
});

it('refuses deleting categories still used by tickets', function () {
    $category = Category::factory()->create();
    Ticket::factory()->for($category)->open()->create();

    $this->actingAs(User::factory()->admin()->create())
        ->delete(route('admin.categories.destroy', $category))
        ->assertRedirect()
        ->assertSessionHas('error');

    expect(Category::find($category->id))->not->toBeNull();
});

it('deletes unused categories', function () {
    $category = Category::factory()->create();

    $this->actingAs(User::factory()->admin()->create())
        ->delete(route('admin.categories.destroy', $category))
        ->assertRedirect(route('admin.categories.index'))
        ->assertSessionHas('success');

    expect(Category::find($category->id))->toBeNull();
});
