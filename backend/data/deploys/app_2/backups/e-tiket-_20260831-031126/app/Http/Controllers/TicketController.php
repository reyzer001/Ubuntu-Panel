<?php

namespace App\Http\Controllers;

use App\Models\Category;
use App\Models\Ticket;
use App\Models\TicketLog;
use App\Models\User;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Gate;
use Illuminate\View\View;

class TicketController extends Controller
{
    /**
     * Display a listing of tickets.
     */
    public function index(Request $request): View
    {
        $user = Auth::user();
        $query = Ticket::with(['creator', 'division', 'category', 'technician']);

        // Scope tickets based on role
        if ($user->isDivisionHead()) {
            $query->where('division_id', $user->division_id);
        }

        // Apply filters
        if ($request->filled('status')) {
            $query->where('status', $request->status);
        }
        if ($request->filled('priority')) {
            $query->where('priority', $request->priority);
        }
        if ($request->filled('category_id')) {
            $query->where('category_id', $request->category_id);
        }

        $tickets = $query->orderBy('created_at', 'desc')->paginate(15)->withQueryString();
        $categories = Category::all();

        return view('tickets.index', compact('tickets', 'categories'));
    }

    /**
     * Show the form for creating a new ticket.
     */
    public function create(): View
    {
        Gate::authorize('create', Ticket::class);

        $categories = Category::all();

        return view('tickets.create', compact('categories'));
    }

    /**
     * Store a newly created ticket.
     */
    public function store(Request $request): RedirectResponse
    {
        Gate::authorize('create', Ticket::class);

        $request->validate([
            'category_id' => ['required', 'exists:categories,id'],
            'subject' => ['required', 'string', 'max:255'],
            'description' => ['required', 'string'],
            'location' => ['required', 'string', 'max:255'],
            'asset_code' => ['nullable', 'string', 'max:100'],
            'priority' => ['required', 'in:low,medium,high,emergency'],
        ]);

        $user = Auth::user();

        // Generate a unique ticket number: TKT-YYYYMMDD-XXXX (retries on race condition)
        $todayDate = date('Ymd');
        $ticket = null;

        for ($attempt = 0; $attempt < 5 && $ticket === null; $attempt++) {
            $ticketCountToday = Ticket::where('ticket_number', 'like', "TKT-{$todayDate}-%")->count();
            $sequence = str_pad((string) ($ticketCountToday + 1 + $attempt), 4, '0', STR_PAD_LEFT);
            $ticketNumber = "TKT-{$todayDate}-{$sequence}";

            try {
                $ticket = Ticket::create([
                    'ticket_number' => $ticketNumber,
                    'creator_id' => $user->id,
                    'division_id' => $user->division_id,
                    'category_id' => $request->category_id,
                    'subject' => $request->subject,
                    'description' => $request->description,
                    'location' => $request->location,
                    'asset_code' => $request->asset_code,
                    'priority' => $request->priority,
                    'status' => Ticket::STATUS_OPEN,
                ]);
            } catch (UniqueConstraintViolationException) {
                $ticket = null;
            }
        }

        if ($ticket === null) {
            return back()->with('error', 'Gagal membuat nomor tiket karena konflik data. Silakan coba lagi.');
        }

        // Create log
        TicketLog::create([
            'ticket_id' => $ticket->id,
            'user_id' => $user->id,
            'action' => 'Pelaporan Tiket',
            'note' => 'Tiket berhasil dibuat oleh '.$user->name,
        ]);

        return redirect()->route('tickets.show', $ticket)->with('success', "Tiket {$ticket->ticket_number} berhasil dilaporkan.");
    }

    /**
     * Display the specified ticket.
     */
    public function show(Ticket $ticket): View
    {
        Gate::authorize('view', $ticket);

        $ticket->load(['creator', 'division', 'category', 'technician', 'logs.user']);
        $technicians = User::where('role', User::ROLE_TECHNICIAN)->where('is_active', true)->get();

        return view('tickets.show', compact('ticket', 'technicians'));
    }

    /**
     * Assign a ticket to a technician (Admin only).
     */
    public function assign(Request $request, Ticket $ticket): RedirectResponse
    {
        Gate::authorize('assign', $ticket);

        $request->validate([
            'technician_id' => ['required', 'exists:users,id'],
        ]);

        $technician = User::findOrFail($request->technician_id);

        if (! $technician->isTechnician()) {
            return back()->with('error', 'Pengguna yang dipilih bukan seorang teknisi.');
        }

        $ticket->update([
            'technician_id' => $technician->id,
            'status' => Ticket::STATUS_ASSIGNED,
            'assigned_at' => now(),
        ]);

        TicketLog::create([
            'ticket_id' => $ticket->id,
            'user_id' => Auth::id(),
            'action' => 'Penugasan Teknisi',
            'note' => 'Admin menugaskan tiket kepada '.$technician->name,
        ]);

        return back()->with('success', 'Teknisi berhasil ditugaskan.');
    }

    /**
     * Update ticket status (Technician / Admin).
     */
    public function updateStatus(Request $request, Ticket $ticket): RedirectResponse
    {
        Gate::authorize('respond', $ticket);

        $request->validate([
            'status' => ['required', 'in:in_progress,pending,resolved'],
            'note' => ['required_if:status,pending,resolved', 'nullable', 'string'],
        ]);

        $status = $request->status;
        $updates = ['status' => $status];

        if ($status === Ticket::STATUS_IN_PROGRESS && ! $ticket->started_at) {
            $updates['started_at'] = now();
        } elseif ($status === Ticket::STATUS_RESOLVED) {
            $updates['resolved_at'] = now();
        }

        $ticket->update($updates);

        $actionWord = match ($status) {
            Ticket::STATUS_IN_PROGRESS => 'Mulai Penanganan',
            Ticket::STATUS_PENDING => 'Penundaan Pekerjaan',
            Ticket::STATUS_RESOLVED => 'Penyelesaian Masalah',
        };

        TicketLog::create([
            'ticket_id' => $ticket->id,
            'user_id' => Auth::id(),
            'action' => $actionWord,
            'note' => $request->note ?? 'Status tiket diperbarui menjadi: '.str_replace('_', ' ', $status),
        ]);

        return back()->with('success', 'Status tiket berhasil diperbarui.');
    }

    /**
     * Close the ticket (Division Head / Admin).
     */
    public function close(Request $request, Ticket $ticket): RedirectResponse
    {
        Gate::authorize('close', $ticket);

        if ($ticket->status !== Ticket::STATUS_RESOLVED) {
            return back()->with('error', 'Hanya tiket berstatus Resolved yang dapat ditutup.');
        }

        DB::transaction(function () use ($ticket): void {
            $ticket->update([
                'status' => Ticket::STATUS_CLOSED,
                'closed_at' => now(),
            ]);

            TicketLog::create([
                'ticket_id' => $ticket->id,
                'user_id' => Auth::id(),
                'action' => 'Penutupan Tiket',
                'note' => 'Tiket dikonfirmasi selesai dan ditutup.',
            ]);
        });

        return back()->with('success', 'Tiket telah berhasil ditutup.');
    }

    /**
     * Re-open the ticket if unresolved (Division Head / Admin).
     */
    public function reopen(Request $request, Ticket $ticket): RedirectResponse
    {
        Gate::authorize('close', $ticket);

        if ($ticket->status !== Ticket::STATUS_CLOSED) {
            return back()->with('error', 'Hanya tiket yang telah ditutup yang dapat dibuka kembali.');
        }

        $request->validate([
            'note' => ['required', 'string'],
        ]);

        $ticket->update([
            'status' => Ticket::STATUS_IN_PROGRESS,
            'resolved_at' => null,
            'closed_at' => null,
        ]);

        TicketLog::create([
            'ticket_id' => $ticket->id,
            'user_id' => Auth::id(),
            'action' => 'Membuka Kembali Tiket',
            'note' => 'Tiket dibuka kembali dengan alasan: '.$request->note,
        ]);

        return back()->with('success', 'Tiket dibuka kembali untuk penanganan lebih lanjut.');
    }
}
