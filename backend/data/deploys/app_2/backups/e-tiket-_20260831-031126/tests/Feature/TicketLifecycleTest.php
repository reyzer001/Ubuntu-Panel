<?php

use App\Models\Category;
use App\Models\Ticket;
use App\Models\User;
use Illuminate\Support\Str;

uses()->group('tickets');

function actingDivisionHead(): User
{
    return User::factory()->divisionHead()->create();
}

function validTicketPayload(Category $category): array
{
    return [
        'category_id' => $category->id,
        'subject' => 'Gangguan PC Poli Anak',
        'description' => 'PC tidak bisa boot sejak pagi.',
        'location' => 'Poliklinik Anak Lt. 2',
        'asset_code' => 'PC-PLK-012',
        'priority' => 'high',
    ];
}

it('allows division heads to create tickets', function () {
    $head = actingDivisionHead();
    $category = Category::factory()->create();

    $response = $this->actingAs($head)
        ->post(route('tickets.store'), validTicketPayload($category));

    $ticket = Ticket::query()->sole();

    $response->assertRedirect(route('tickets.show', $ticket));
    expect(Str::startsWith($ticket->ticket_number, 'TKT-'.date('Ymd').'-'))->toBeTrue()
        ->and($ticket->status)->toBe(Ticket::STATUS_OPEN)
        ->and($ticket->creator_id)->toBe($head->id)
        ->and($ticket->division_id)->toBe($head->division_id)
        ->and($ticket->logs()->count())->toBe(1);
});

it('forbids admins and technicians from creating tickets', function () {
    $category = Category::factory()->create();

    foreach ([User::factory()->admin(), User::factory()->technician()] as $user) {
        $this->actingAs($user->create())
            ->post(route('tickets.store'), validTicketPayload($category))
            ->assertForbidden();
    }

    expect(Ticket::count())->toBe(0);
});

it('validates ticket input', function () {
    $this->actingAs(actingDivisionHead())
        ->from('/tickets/create')
        ->post(route('tickets.store'), [])
        ->assertRedirect('/tickets/create')
        ->assertSessionHasErrors(['category_id', 'subject', 'description', 'location', 'priority']);
});

it('scopes the ticket list to the division for division heads', function () {
    $head = User::factory()->divisionHead()->create();
    $own = Ticket::factory()->create(['creator_id' => $head->id, 'division_id' => $head->division_id]);
    $other = Ticket::factory()->create(); // other division

    $this->actingAs($head)
        ->get(route('tickets.index'))
        ->assertOk()
        ->assertSee($own->ticket_number)
        ->assertDontSee($other->ticket_number);
});

it('lets admins assign technicians', function () {
    $technician = User::factory()->technician()->create();
    $ticket = Ticket::factory()->open()->create();

    $this->actingAs(User::factory()->admin()->create())
        ->post(route('tickets.assign', $ticket), ['technician_id' => $technician->id])
        ->assertRedirect()
        ->assertSessionHas('success');

    expect($ticket->fresh()->technician_id)->toBe($technician->id)
        ->and($ticket->fresh()->status)->toBe(Ticket::STATUS_ASSIGNED);
});

it('rejects assigning non technicians', function () {
    $ticket = Ticket::factory()->open()->create();
    $stranger = User::factory()->divisionHead()->create();

    $this->actingAs(User::factory()->admin()->create())
        ->post(route('tickets.assign', $ticket), ['technician_id' => $stranger->id])
        ->assertRedirect()
        ->assertSessionHas('error');

    expect($ticket->fresh()->technician_id)->toBeNull();
});

it('walks the full ticket lifecycle to closure', function () {
    $technician = User::factory()->technician()->create();
    $admin = User::factory()->admin()->create();
    $ticket = Ticket::factory()->open()->create();

    // Assign
    $this->actingAs($admin)->post(route('tickets.assign', $ticket), [
        'technician_id' => $technician->id,
    ]);

    // Start working
    $this->actingAs($technician)
        ->patch(route('tickets.status', $ticket), ['status' => 'in_progress'])
        ->assertRedirect()
        ->assertSessionHas('success');
    expect($ticket->fresh()->status)->toBe(Ticket::STATUS_IN_PROGRESS)
        ->and($ticket->fresh()->started_at)->not->toBeNull();

    // Pending requires a note
    $this->patch(route('tickets.status', $ticket), ['status' => 'pending'])
        ->assertSessionHasErrors('note');

    $this->patch(route('tickets.status', $ticket), ['status' => 'pending', 'note' => 'Menunggu sparepart.'])
        ->assertSessionHas('success');
    expect($ticket->fresh()->status)->toBe(Ticket::STATUS_PENDING);

    // Resolve with a solution note
    $this->patch(route('tickets.status', $ticket), ['status' => 'resolved', 'note' => 'Ganti power supply.'])
        ->assertSessionHas('success');
    expect($ticket->fresh()->status)->toBe(Ticket::STATUS_RESOLVED)
        ->and($ticket->fresh()->resolved_at)->not->toBeNull();

    // Creator closes it without rating
    $this->actingAs(User::find($ticket->creator_id))
        ->patch(route('tickets.close', $ticket))
        ->assertSessionHas('success');

    $ticket->refresh();
    expect($ticket->status)->toBe(Ticket::STATUS_CLOSED)
        ->and($ticket->closed_at)->not->toBeNull();
});

it('refuses closing tickets that are not resolved', function () {
    $ticket = Ticket::factory()->inProgress()->create();

    $this->actingAs(User::find($ticket->creator_id))
        ->patch(route('tickets.close', $ticket))
        ->assertRedirect()
        ->assertSessionHas('error');

    expect($ticket->fresh()->status)->toBe(Ticket::STATUS_IN_PROGRESS);
});

it('reopens closed tickets', function () {
    $ticket = Ticket::factory()->closed()->create([
        'creator_id' => User::factory()->divisionHead(),
    ]);
    $this->actingAs(User::find($ticket->creator_id))
        ->patch(route('tickets.reopen', $ticket), ['note' => 'Masalah terulang.'])
        ->assertSessionHas('success');

    expect($ticket->fresh()->status)->toBe(Ticket::STATUS_IN_PROGRESS)
        ->and($ticket->fresh()->closed_at)->toBeNull()
        ->and($ticket->fresh()->resolved_at)->toBeNull();
});

it('prevents unauthorized status updates', function () {
    $ticket = Ticket::factory()->assigned()->create();
    $otherTechnician = User::factory()->technician()->create();

    $this->actingAs($otherTechnician)
        ->patch(route('tickets.status', $ticket), ['status' => 'resolved', 'note' => 'hack'])
        ->assertForbidden();

    expect($ticket->fresh()->status)->toBe(Ticket::STATUS_ASSIGNED);
});
