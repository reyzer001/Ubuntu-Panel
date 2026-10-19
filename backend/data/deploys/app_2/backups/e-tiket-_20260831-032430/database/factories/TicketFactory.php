<?php

namespace Database\Factories;

use App\Models\Category;
use App\Models\Ticket;
use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Ticket>
 */
class TicketFactory extends Factory
{
    /**
     * Running sequence for generated ticket numbers.
     */
    protected static int $numberSequence = 0;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'ticket_number' => 'TKT-'.date('Ymd').'-'.str_pad((string) ++static::$numberSequence, 4, '0', STR_PAD_LEFT),
            'creator_id' => User::factory()->divisionHead(),
            'technician_id' => null,
            'division_id' => fn (array $attributes) => User::find($attributes['creator_id'])->division_id,
            'category_id' => Category::factory(),
            'subject' => fake()->sentence(),
            'description' => fake()->paragraph(),
            'location' => fake()->randomElement(['IGD', 'Poliklinik', 'Ruang Rawat Inap', 'Farmasi', 'Laboratorium']),
            'asset_code' => null,
            'priority' => fake()->randomElement(['low', 'medium', 'high']),
            'status' => Ticket::STATUS_OPEN,
        ];
    }

    /**
     * Indicate the ticket is open.
     */
    public function open(): static
    {
        return $this->state(fn () => ['status' => Ticket::STATUS_OPEN]);
    }

    /**
     * Indicate the ticket has been assigned to a technician.
     */
    public function assigned(): static
    {
        return $this->state(fn () => [
            'status' => Ticket::STATUS_ASSIGNED,
            'technician_id' => User::factory()->technician(),
            'assigned_at' => now(),
        ]);
    }

    /**
     * Indicate the ticket is being worked on by the assigned technician.
     */
    public function inProgress(): static
    {
        return $this->assigned()->state(fn () => [
            'status' => Ticket::STATUS_IN_PROGRESS,
            'started_at' => now(),
        ]);
    }

    /**
     * Indicate the ticket is pending.
     */
    public function pending(): static
    {
        return $this->inProgress()->state(fn () => ['status' => Ticket::STATUS_PENDING]);
    }

    /**
     * Indicate the ticket has been resolved.
     */
    public function resolved(): static
    {
        return $this->state(fn (array $attributes) => [
            'status' => Ticket::STATUS_RESOLVED,
            'resolved_at' => now(),
        ]);
    }

    /**
     * Indicate the ticket is closed.
     */
    public function closed(): static
    {
        return $this->state(fn () => [
            'status' => Ticket::STATUS_CLOSED,
            'resolved_at' => now(),
            'closed_at' => now(),
        ]);
    }
}
