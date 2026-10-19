@extends('layouts.app')

@section('title', 'Kelola Tiket')
@section('page-title', 'Kelola Tiket')
@section('page-subtitle', 'Daftar seluruh tiket pelaporan kendala IT')

@section('content')
<div class="space-y-6">

    <!-- Filter Bar -->
    <div class="bg-white rounded-xl border border-gray-200 p-4 fade-in">
        <form method="GET" action="{{ route('tickets.index') }}" class="flex flex-col md:flex-row md:items-end gap-3">
            <div class="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                    <label for="status" class="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Status</label>
                    <select name="status" id="status" class="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white text-gray-700 focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer hover:border-gray-400 transition-colors">
                        <option value="">Semua Status</option>
                        @foreach(['open' => 'Open', 'assigned' => 'Assigned', 'in_progress' => 'In Progress', 'pending' => 'Pending', 'resolved' => 'Resolved', 'closed' => 'Closed'] as $value => $label)
                            <option value="{{ $value }}" @selected(request('status') === $value)>{{ $label }}</option>
                        @endforeach
                    </select>
                </div>
                <div>
                    <label for="priority" class="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Prioritas</label>
                    <select name="priority" id="priority" class="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white text-gray-700 focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer hover:border-gray-400 transition-colors">
                        <option value="">Semua Prioritas</option>
                        @foreach(['low' => 'Low', 'medium' => 'Medium', 'high' => 'High', 'emergency' => 'Emergency'] as $value => $label)
                            <option value="{{ $value }}" @selected(request('priority') === $value)>{{ $label }}</option>
                        @endforeach
                    </select>
                </div>
                <div>
                    <label for="category_id" class="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Kategori</label>
                    <select name="category_id" id="category_id" class="w-full text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white text-gray-700 focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer hover:border-gray-400 transition-colors">
                        <option value="">Semua Kategori</option>
                        @foreach($categories as $category)
                            <option value="{{ $category->id }}" @selected(request('category_id') == $category->id)>{{ $category->name }}</option>
                        @endforeach
                    </select>
                </div>
            </div>
            <div class="flex gap-2">
                <button type="submit" class="px-4 py-2 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 flex items-center gap-2 whitespace-nowrap">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                    Filter
                </button>
                <a href="{{ route('tickets.index') }}" class="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors whitespace-nowrap">Reset</a>
            </div>
        </form>
    </div>

    <!-- Tickets Table -->
    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden fade-in" style="animation-delay: 0.1s">
        <div class="px-6 py-5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
                <h3 class="text-lg font-bold text-gray-900">Daftar Tiket</h3>
                <p class="text-sm text-gray-500">Menampilkan {{ $tickets->firstItem() ?? 0 }} - {{ $tickets->lastItem() ?? 0 }} dari {{ number_format($tickets->total(), 0, ',', '.') }} tiket</p>
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
                        <th class="px-6 py-4">Divisi</th>
                        <th class="px-6 py-4">Kategori</th>
                        <th class="px-6 py-4">Petugas</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4">Prioritas</th>
                        <th class="px-6 py-4">Tanggal</th>
                        <th class="px-6 py-4 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                    @forelse($tickets as $ticket)
                        <tr class="hover:bg-gray-50 transition-colors">
                            <td class="px-6 py-4 font-mono font-medium text-emerald-700 whitespace-nowrap">{{ $ticket->ticket_number }}</td>
                            <td class="px-6 py-4 font-medium text-gray-900 max-w-[240px] truncate">{{ $ticket->subject }}</td>
                            <td class="px-6 py-4 text-gray-600 whitespace-nowrap">{{ Str::limit($ticket->division->name, 22) }}</td>
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
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-teal-500"></span>Resolved</span>
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
                            <td colspan="9" class="px-6 py-12 text-center text-gray-400">
                                <svg class="w-12 h-12 mx-auto text-gray-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                                <p class="font-semibold text-gray-500">Tidak ada tiket yang cocok dengan filter.</p>
                            </td>
                        </tr>
                    @endforelse
                </tbody>
            </table>
        </div>
        @if($tickets->hasPages())
            <div class="px-6 py-4 border-t border-gray-200">
                {{ $tickets->links() }}
            </div>
        @endif
    </div>

</div>
@endsection
