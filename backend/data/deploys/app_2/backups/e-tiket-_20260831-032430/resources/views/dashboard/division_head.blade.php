@extends('layouts.app')

@section('title', 'Dashboard Divisi')
@section('page-title', 'Dashboard Unit Divisi')
@section('page-subtitle', 'Monitoring tiket pelaporan unit Anda')

@section('content')
<div class="space-y-6">

    <!-- Stats Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-6">
        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-emerald-50 rounded-lg">
                    <svg class="w-6 h-6 text-emerald-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3"/></svg>
                </div>
                <span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full">Total</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ $stats['total'] }}</h3>
            <p class="text-sm text-gray-500 mt-1">Total Tiket</p>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.1s">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-amber-50 rounded-lg">
                    <svg class="w-6 h-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </div>
                <span class="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-1 rounded-full">Open</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ $stats['open'] }}</h3>
            <p class="text-sm text-gray-500 mt-1">Menunggu Ditugaskan</p>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.2s">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-emerald-50 rounded-lg">
                    <svg class="w-6 h-6 text-emerald-800" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                </div>
                <span class="text-xs font-medium text-emerald-800 bg-emerald-50 px-2 py-1 rounded-full">Aktif</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ $stats['active'] }}</h3>
            <p class="text-sm text-gray-500 mt-1">Sedang Ditangani</p>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.3s">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-teal-50 rounded-lg">
                    <svg class="w-6 h-6 text-teal-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                </div>
                <span class="text-xs font-medium text-teal-700 bg-teal-50 px-2 py-1 rounded-full">Resolved</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ $stats['resolved'] }}</h3>
            <p class="text-sm text-gray-500 mt-1">Menunggu Konfirmasi</p>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.4s">
            <div class="flex items-center justify-between mb-4">
                <div class="p-2.5 bg-emerald-50 rounded-lg">
                    <svg class="w-6 h-6 text-emerald-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                </div>
                <span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full">Closed</span>
            </div>
            <h3 class="text-2xl font-bold text-gray-900">{{ $stats['closed'] }}</h3>
            <p class="text-sm text-gray-500 mt-1">Tiket Selesai</p>
        </div>
    </div>

    <!-- Division Tickets Table -->
    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden fade-in" style="animation-delay: 0.5s">
        <div class="px-6 py-5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
                <h3 class="text-lg font-bold text-gray-900">Tiket Divisi</h3>
                <p class="text-sm text-gray-500">15 laporan terbaru dari unit Anda</p>
            </div>
            @can('create', App\Models\Ticket::class)
                <a href="{{ route('tickets.create') }}" class="px-4 py-2 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 flex items-center gap-2 whitespace-nowrap self-start sm:self-auto">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                    Buat Tiket
                </a>
            @endcan
        </div>
        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
                <thead class="bg-gray-50 text-gray-700 uppercase text-xs font-semibold">
                    <tr>
                        <th class="px-6 py-4">ID Tiket</th>
                        <th class="px-6 py-4">Judul / Keluhan</th>
                        <th class="px-6 py-4">Kategori</th>
                        <th class="px-6 py-4">Petugas</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4">Prioritas</th>
                        <th class="px-6 py-4">Tanggal</th>
                        <th class="px-6 py-4 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                    @forelse($divisionTickets as $ticket)
                        <tr class="hover:bg-gray-50 transition-colors">
                            <td class="px-6 py-4 font-mono font-medium text-emerald-700 whitespace-nowrap">{{ $ticket->ticket_number }}</td>
                            <td class="px-6 py-4 font-medium text-gray-900 max-w-[240px] truncate">{{ $ticket->subject }}</td>
                            <td class="px-6 py-4">
                                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-100 whitespace-nowrap">{{ Str::limit($ticket->category->name, 18) }}</span>
                            </td>
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
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-teal-500 animate-pulse"></span>Resolved</span>
                                @else
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Closed</span>
                                @endif
                            </td>
                            <td class="px-6 py-4">
                                @if($ticket->priority === 'emergency')
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-800 border border-red-200 whitespace-nowrap">Emergency</span>
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
                            <td colspan="8" class="px-6 py-12 text-center text-gray-400">
                                <svg class="w-12 h-12 mx-auto text-gray-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                                <p class="font-semibold text-gray-500">Belum ada tiket dari divisi Anda.</p>
                                <p class="text-xs">Laporkan kendala IT melalui tombol "Buat Tiket".</p>
                            </td>
                        </tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </div>

</div>
@endsection
