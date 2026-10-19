<?php

namespace App\Http\Controllers;

use App\Models\Category;
use App\Models\Ticket;
use App\Models\TicketLog;
use App\Models\User;
use Carbon\Carbon;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Str;
use Illuminate\View\View;

class DashboardController extends Controller
{
    /**
     * SQL expression that sorts tickets by priority weight instead of alphabetically.
     */
    private const PRIORITY_ORDER = "CASE priority WHEN 'emergency' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END";

    /**
     * Show the application dashboard.
     */
    public function index(): View
    {
        $user = Auth::user();

        if ($user->isAdmin()) {
            return $this->adminDashboard();
        } elseif ($user->isTechnician()) {
            return $this->technicianDashboard($user);
        } else {
            return $this->divisionHeadDashboard($user);
        }
    }

    /**
     * Admin / Kepala IT Dashboard.
     */
    private function adminDashboard(): View
    {
        $stats = [
            'total' => Ticket::count(),
            'open' => Ticket::where('status', Ticket::STATUS_OPEN)->count(),
            'assigned' => Ticket::where('status', Ticket::STATUS_ASSIGNED)->count(),
            'in_progress' => Ticket::where('status', Ticket::STATUS_IN_PROGRESS)->count(),
            'pending' => Ticket::where('status', Ticket::STATUS_PENDING)->count(),
            'resolved' => Ticket::where('status', Ticket::STATUS_RESOLVED)->count(),
            'closed' => Ticket::where('status', Ticket::STATUS_CLOSED)->count(),
            'emergency' => Ticket::where('priority', Ticket::PRIORITY_EMERGENCY)
                ->whereNotIn('status', [Ticket::STATUS_RESOLVED, Ticket::STATUS_CLOSED])
                ->count(),
        ];

        // Load active tickets (unresolved)
        $activeTickets = Ticket::with(['creator', 'division', 'category', 'technician'])
            ->whereNotIn('status', [Ticket::STATUS_CLOSED])
            ->orderByRaw(self::PRIORITY_ORDER)
            ->orderBy('created_at', 'desc')
            ->take(10)
            ->get();

        // Load list of technicians with their current workload
        $technicians = User::where('role', User::ROLE_TECHNICIAN)
            ->where('is_active', true)
            ->withCount(['assignedTickets' => function ($query) {
                $query->whereNotIn('status', [Ticket::STATUS_RESOLVED, Ticket::STATUS_CLOSED]);
            }])
            ->get();

        // Calculate SLA status (simple metrics)
        $allActiveTickets = Ticket::with('category')
            ->whereNotIn('status', [Ticket::STATUS_RESOLVED, Ticket::STATUS_CLOSED])
            ->get();

        $slaBreachedCount = 0;
        foreach ($allActiveTickets as $ticket) {
            $limitMinutes = $ticket->category->sla_resolve_minutes;
            $elapsedMinutes = Carbon::parse($ticket->created_at)->diffInMinutes(now());
            if ($elapsedMinutes > $limitMinutes) {
                $slaBreachedCount++;
            }
        }

        // Monthly trend: tickets created vs resolved (last 6 months)
        $monthLabels = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
        $trendLabels = [];
        $trendMasuk = [];
        $trendSelesai = [];

        for ($i = 5; $i >= 0; $i--) {
            $start = now()->subMonthsNoOverflow($i)->startOfMonth();
            $end = now()->subMonthsNoOverflow($i)->endOfMonth();

            $trendLabels[] = $monthLabels[$start->month - 1];
            $trendMasuk[] = Ticket::whereBetween('created_at', [$start, $end])->count();
            $trendSelesai[] = Ticket::whereBetween('resolved_at', [$start, $end])->count();
        }

        // Status distribution for pie chart
        $statusDistribution = [
            ['name' => 'Open', 'value' => $stats['open'] + $stats['assigned'], 'color' => '#047857'],
            ['name' => 'In Progress', 'value' => $stats['in_progress'], 'color' => '#065f46'],
            ['name' => 'Pending', 'value' => $stats['pending'], 'color' => '#f59e0b'],
            ['name' => 'Selesai', 'value' => $stats['resolved'] + $stats['closed'], 'color' => '#10b981'],
        ];

        // Tickets per category
        $categoriesWithCount = Category::withCount('tickets')->orderByDesc('tickets_count')->get();
        $categoryNames = $categoriesWithCount->pluck('name')->reverse()->values()->toArray();
        $categoryCounts = $categoriesWithCount->pluck('tickets_count')->reverse()->values()->toArray();

        // Chart payload for ECharts (consumed by resources/js/dashboard.js)
        $chartData = [
            'trendLabels' => $trendLabels,
            'trendMasuk' => $trendMasuk,
            'trendSelesai' => $trendSelesai,
            'statusDistribution' => collect($statusDistribution)
                ->map(fn (array $item) => [
                    'value' => $item['value'],
                    'name' => $item['name'],
                    'itemStyle' => ['color' => $item['color']],
                ])
                ->values(),
            'categoryNames' => array_map(
                fn (string $name) => Str::limit($name, 22),
                $categoryNames
            ),
            'categoryCounts' => $categoryCounts,
        ];

        // Recent tickets (any status)
        $recentTickets = Ticket::with(['creator', 'division', 'category', 'technician'])
            ->orderBy('created_at', 'desc')
            ->take(6)
            ->get();

        // Latest activity logs
        $activities = TicketLog::with(['user', 'ticket'])->orderBy('created_at', 'desc')->take(5)->get();

        return view('dashboard.admin', compact(
            'stats', 'activeTickets', 'technicians', 'slaBreachedCount',
            'statusDistribution', 'chartData', 'recentTickets', 'activities'
        ));
    }

    /**
     * Technician IT Dashboard.
     */
    private function technicianDashboard(User $user): View
    {
        $stats = [
            'total' => Ticket::where('technician_id', $user->id)->count(),
            'assigned' => Ticket::where('technician_id', $user->id)->where('status', Ticket::STATUS_ASSIGNED)->count(),
            'in_progress' => Ticket::where('technician_id', $user->id)->where('status', Ticket::STATUS_IN_PROGRESS)->count(),
            'pending' => Ticket::where('technician_id', $user->id)->where('status', Ticket::STATUS_PENDING)->count(),
            'resolved' => Ticket::where('technician_id', $user->id)->where('status', Ticket::STATUS_RESOLVED)->count(),
        ];

        // Technician tasks
        $myTickets = Ticket::with(['creator', 'division', 'category'])
            ->where('technician_id', $user->id)
            ->whereNotIn('status', [Ticket::STATUS_CLOSED])
            ->orderByRaw(self::PRIORITY_ORDER)
            ->orderBy('created_at', 'desc')
            ->get();

        return view('dashboard.technician', compact('stats', 'myTickets'));
    }

    /**
     * Kepala Unit Divisi Dashboard.
     */
    private function divisionHeadDashboard(User $user): View
    {
        $divisionId = $user->division_id;

        $stats = [
            'total' => Ticket::where('division_id', $divisionId)->count(),
            'open' => Ticket::where('division_id', $divisionId)->where('status', Ticket::STATUS_OPEN)->count(),
            'active' => Ticket::where('division_id', $divisionId)
                ->whereIn('status', [Ticket::STATUS_ASSIGNED, Ticket::STATUS_IN_PROGRESS, Ticket::STATUS_PENDING])
                ->count(),
            'resolved' => Ticket::where('division_id', $divisionId)->where('status', Ticket::STATUS_RESOLVED)->count(),
            'closed' => Ticket::where('division_id', $divisionId)->where('status', Ticket::STATUS_CLOSED)->count(),
        ];

        // Division tickets
        $divisionTickets = Ticket::with(['category', 'technician'])
            ->where('division_id', $divisionId)
            ->orderBy('created_at', 'desc')
            ->take(15)
            ->get();

        return view('dashboard.division_head', compact('stats', 'divisionTickets'));
    }
}
