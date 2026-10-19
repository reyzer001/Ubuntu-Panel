@extends('layouts.app')

@section('title', 'Dashboard Monitoring')
@section('page-title', 'Dashboard Monitoring')
@section('page-subtitle', 'Overview tiket dan pelaporan real-time')

@section('content')
<div class="space-y-6">

    <!-- Alarm & Warning Section -->
    @if($slaBreachedCount > 0 || $stats['emergency'] > 0)
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            @if($stats['emergency'] > 0)
                <div class="p-4 bg-red-50 border border-red-200 text-red-900 rounded-xl flex items-start gap-3 fade-in">
                    <svg class="w-6 h-6 text-red-600 shrink-0 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
                    </svg>
                    <div>
                        <p class="font-bold">Tiket Emergency Aktif!</p>
                        <p class="text-sm text-red-800">Terdapat <span class="font-bold">{{ $stats['emergency'] }} tiket prioritas darurat</span> yang belum terselesaikan. Segera instruksikan teknisi siaga.</p>
                    </div>
                </div>
            @endif

            @if($slaBreachedCount > 0)
                <div class="p-4 bg-amber-50 border border-amber-200 text-amber-900 rounded-xl flex items-start gap-3 fade-in">
                    <svg class="w-6 h-6 text-amber-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                    </svg>
                    <div>
                        <p class="font-bold">Peringatan Batas Waktu SLA!</p>
                        <p class="text-sm text-amber-800">Terdapat <span class="font-bold">{{ $slaBreachedCount }} tiket aktif</span> yang telah melampaui estimasi waktu penyelesaian (SLA).</p>
                    </div>
                </div>
            @endif
        </div>
    @endif

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-emerald-50 rounded-lg">
                    <svg class="w-6 h-6 text-emerald-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
                </div>
                <span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full">Total</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ number_format($stats['total'], 0, ',', '.') }}</h3>
            <p class="text-sm text-gray-500 mt-1">Total Tiket</p>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.1s">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-amber-50 rounded-lg">
                    <svg class="w-6 h-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </div>
                <span class="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-1 rounded-full">Open</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ $stats['open'] + $stats['assigned'] }}</h3>
            <p class="text-sm text-gray-500 mt-1">Tiket Open</p>
            <div class="mt-3 w-full bg-gray-200 rounded-full h-1.5">
                <div class="bg-amber-500 h-1.5 rounded-full transition-all duration-1000" style="width: {{ $stats['total'] > 0 ? round((($stats['open'] + $stats['assigned']) / $stats['total']) * 100) : 0 }}%"></div>
            </div>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.2s">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-emerald-50 rounded-lg">
                    <svg class="w-6 h-6 text-emerald-800" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                </div>
                <span class="text-xs font-medium text-emerald-800 bg-emerald-50 px-2 py-1 rounded-full">Dikerjakan</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ $stats['in_progress'] + $stats['pending'] }}</h3>
            <p class="text-sm text-gray-500 mt-1">In Progress / Pending</p>
            <div class="mt-3 w-full bg-gray-200 rounded-full h-1.5">
                <div class="bg-emerald-700 h-1.5 rounded-full transition-all duration-1000" style="width: {{ $stats['total'] > 0 ? round((($stats['in_progress'] + $stats['pending']) / $stats['total']) * 100) : 0 }}%"></div>
            </div>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.3s">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-emerald-50 rounded-lg">
                    <svg class="w-6 h-6 text-emerald-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </div>
                <span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full">Selesai</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ number_format($stats['resolved'] + $stats['closed'], 0, ',', '.') }}</h3>
            <p class="text-sm text-gray-500 mt-1">Tiket Closed</p>
            <div class="mt-3 flex items-center text-sm text-emerald-700 font-medium">
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>
                <span>Tingkat penyelesaian {{ $stats['total'] > 0 ? round((($stats['resolved'] + $stats['closed']) / $stats['total']) * 100, 1) : 0 }}%</span>
            </div>
        </div>
    </div>

    <!-- Charts Row -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Line Chart -->
        <div class="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.4s">
            <div class="mb-6">
                <h3 class="text-lg font-bold text-gray-900">Trend Tiket Bulanan</h3>
                <p class="text-sm text-gray-500">Rekapitulasi tiket masuk vs selesai 6 bulan terakhir</p>
            </div>
            <div class="h-72 w-full" id="trendChart"></div>
        </div>

        <!-- Pie Chart -->
        <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.5s">
            <div class="mb-6">
                <h3 class="text-lg font-bold text-gray-900">Distribusi Status</h3>
                <p class="text-sm text-gray-500">Persentase berdasarkan status tiket</p>
            </div>
            <div class="h-56 w-full flex items-center justify-center" id="statusChart"></div>
            <div class="mt-4 grid grid-cols-2 gap-3">
                @foreach($statusDistribution as $item)
                    <div class="flex items-center gap-2 text-sm">
                        <span class="w-3 h-3 rounded-full" style="background-color: {{ $item['color'] }}"></span>
                        <span class="text-gray-600">{{ $item['name'] }}</span>
                        <span class="ml-auto font-semibold text-gray-900">{{ number_format($item['value'], 0, ',', '.') }}</span>
                    </div>
                @endforeach
            </div>
        </div>
    </div>

    <!-- Second Row: Category & Staff Performance -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.6s">
            <h3 class="text-lg font-bold text-gray-900 mb-1">Tiket per Kategori</h3>
            <p class="text-sm text-gray-500 mb-6">Distribusi berdasarkan jenis permasalahan</p>
            <div class="h-64 w-full" id="categoryChart"></div>
        </div>
        <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.7s">
            <h3 class="text-lg font-bold text-gray-900 mb-1">Beban Kerja Teknisi</h3>
            <p class="text-sm text-gray-500 mb-6">Jumlah tiket aktif yang sedang ditangani</p>
            <div class="space-y-4" id="staffPerformance">
                @php
                    $maxWorkload = $technicians->max('assigned_tickets_count') ?: 1;
                @endphp
                @forelse($technicians as $tech)
                    <div class="group">
                        <div class="flex justify-between text-sm mb-1.5">
                            <span class="font-medium text-gray-700 group-hover:text-emerald-600 transition-colors">{{ $tech->name }}</span>
                            <span class="font-semibold text-gray-900">{{ $tech->assigned_tickets_count }} tiket</span>
                        </div>
                        <div class="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                            <div class="bg-gradient-to-r from-emerald-600 to-emerald-800 h-2.5 rounded-full transition-all duration-1000 ease-out" style="width: 0%" data-width="{{ round(($tech->assigned_tickets_count / $maxWorkload) * 100) }}%"></div>
                        </div>
                    </div>
                @empty
                    <p class="text-sm text-gray-400 text-center py-6">Belum ada teknisi terdaftar.</p>
                @endforelse
            </div>
        </div>
    </div>

    <!-- Recent Tickets Table -->
    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden fade-in" style="animation-delay: 0.8s">
        <div class="px-6 py-5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
                <h3 class="text-lg font-bold text-gray-900">Tiket Terkini</h3>
                <p class="text-sm text-gray-500">Daftar tiket terbaru yang memerlukan perhatian</p>
            </div>
            <a href="{{ route('tickets.index') }}" class="px-4 py-2 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 flex items-center gap-2 whitespace-nowrap self-start sm:self-auto">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                Lihat Semua
            </a>
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
                <thead class="bg-gray-50 text-gray-700 uppercase text-xs font-semibold">
                    <tr>
                        <th class="px-6 py-4">ID Tiket</th>
                        <th class="px-6 py-4">Judul / Keluhan</th>
                        <th class="px-6 py-4">Kategori</th>
                        <th class="px-6 py-4">Pengaju</th>
                        <th class="px-6 py-4">Petugas</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4">Prioritas</th>
                        <th class="px-6 py-4">Tanggal</th>
                        <th class="px-6 py-4 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                    @forelse($recentTickets as $ticket)
                        <tr class="hover:bg-gray-50 transition-colors">
                            <td class="px-6 py-4 font-mono font-medium text-emerald-700 whitespace-nowrap">{{ $ticket->ticket_number }}</td>
                            <td class="px-6 py-4 font-medium text-gray-900 max-w-[240px] truncate">{{ $ticket->subject }}</td>
                            <td class="px-6 py-4">
                                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-100 whitespace-nowrap">{{ Str::limit($ticket->category->name, 20) }}</span>
                            </td>
                            <td class="px-6 py-4 text-gray-600 whitespace-nowrap">{{ $ticket->creator->name ?? '-' }}</td>
                            <td class="px-6 py-4 text-gray-600 whitespace-nowrap">{{ $ticket->technician->name ?? '-' }}</td>
                            <td class="px-6 py-4">
                                @if($ticket->status === 'open')
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>Open</span>
                                @elseif($ticket->status === 'assigned')
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sky-50 text-sky-700 border border-sky-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-sky-500"></span>Assigned</span>
                                @elseif($ticket->status === 'in_progress')
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-700 animate-pulse"></span>In Progress</span>
                                @elseif($ticket->status === 'pending')
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-50 text-yellow-700 border border-yellow-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>Pending</span>
                                @elseif($ticket->status === 'resolved')
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-teal-500"></span>Resolved</span>
                                @else
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Closed</span>
                                @endif
                            </td>
                            <td class="px-6 py-4">
                                @if($ticket->priority === 'emergency')
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 border border-red-200 font-bold whitespace-nowrap">Emergency</span>
                                @elseif($ticket->priority === 'high')
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-100 whitespace-nowrap">High</span>
                                @elseif($ticket->priority === 'medium')
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-50 text-orange-700 border border-orange-100 whitespace-nowrap">Medium</span>
                                @else
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-100 whitespace-nowrap">Low</span>
                                @endif
                            </td>
                            <td class="px-6 py-4 text-gray-500 whitespace-nowrap">{{ $ticket->created_at->translatedFormat('d M Y') }}</td>
                            <td class="px-6 py-4 text-right">
                                <a href="{{ route('tickets.show', $ticket) }}" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</a>
                            </td>
                        </tr>
                    @empty
                        <tr>
                            <td colspan="9" class="px-6 py-12 text-center text-gray-400">
                                <p class="font-semibold text-gray-500">Belum ada tiket.</p>
                                <p class="text-xs">Tiket yang dilaporkan akan tampil di sini.</p>
                            </td>
                        </tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </div>

    <!-- Activity Log -->
    <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.9s">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold text-gray-900">Aktivitas Terkini</h3>
        </div>
        <div class="space-y-4">
            @forelse($activities as $activity)
                <div class="flex gap-4 items-start">
                    <div class="w-8 h-8 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center shrink-0 text-xs font-bold">{{ strtoupper(substr($activity->user->name ?? '?', 0, 2)) }}</div>
                    <div class="flex-1 min-w-0">
                        <p class="text-sm text-gray-900">
                            <span class="font-semibold">{{ $activity->user->name ?? 'Sistem' }}</span>
                            {{ $activity->action }}
                            @if($activity->ticket)
                                pada tiket <a href="{{ route('tickets.show', $activity->ticket) }}" class="font-mono text-emerald-700 bg-emerald-50 px-1 rounded hover:bg-emerald-100">{{ $activity->ticket->ticket_number }}</a>
                            @endif
                        </p>
                        <p class="text-xs text-gray-500 mt-0.5">{{ $activity->created_at->diffForHumans() }}</p>
                    </div>
                </div>
            @empty
                <p class="text-sm text-gray-400 text-center py-6">Belum ada aktivitas.</p>
            @endforelse
        </div>
    </div>

</div>
@endsection

@push('scripts')
@vite(['resources/js/dashboard.js'])
<script type="application/json" id="dashboard-data">@json($chartData)</script>
@endpush
