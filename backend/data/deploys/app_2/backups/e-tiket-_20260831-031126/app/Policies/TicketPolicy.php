<?php

namespace App\Policies;

use App\Models\Ticket;
use App\Models\User;

class TicketPolicy
{
    /**
     * Determine whether the user can view completed ticket reports.
     */
    public function viewAny(User $user): bool
    {
        return true;
    }

    /**
     * Determine whether the user can view the ticket.
     */
    public function view(User $user, Ticket $ticket): bool
    {
        if ($user->isAdmin() || $user->isTechnician()) {
            return true;
        }

        return $user->isDivisionHead() && $user->division_id === $ticket->division_id;
    }

    /**
     * Determine whether the user can create tickets.
     */
    public function create(User $user): bool
    {
        return $user->isDivisionHead();
    }

    /**
     * Determine whether the user can assign the ticket.
     */
    public function assign(User $user): bool
    {
        return $user->isAdmin();
    }

    /**
     * Determine whether the user can update the status/respond to the ticket.
     */
    public function respond(User $user, Ticket $ticket): bool
    {
        if ($user->isAdmin()) {
            return true;
        }

        return $user->isTechnician() && $ticket->technician_id === $user->id;
    }

    /**
     * Determine whether the user can close or re-open the ticket.
     */
    public function close(User $user, Ticket $ticket): bool
    {
        if ($user->isAdmin()) {
            return true;
        }

        return $user->isDivisionHead() && $ticket->creator_id === $user->id;
    }
}
