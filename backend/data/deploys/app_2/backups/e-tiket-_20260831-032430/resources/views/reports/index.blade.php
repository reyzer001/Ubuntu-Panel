@extends('layouts.app')

@section('title', 'Rekapan Pekerjaan')
@section('page-title', 'Rekapan Pekerjaan')
@section('page-subtitle', 'Daftar permintaan yang telah diselesaikan')

@section('content')
@php
    $periodLabels = ['monthly' => 'Bulan Ini', 'daily' => 'Hari Ini', 'weekly' => 'Minggu Ini', 'yearly' => 'Tahun Ini', 'custom' => 'Custom'];
@endphp

<div class="space-y-6">
    <div class="bg-white rounded-xl border border-gray-200 p-5">
        <form method="GET" action="{{ route('reports.index') }}" class="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
            <div>
                <label for="period" class="block text-sm font-medium text-gray-700 mb-1">Periode</label>
                <select id="period" name="period" onchange="toggleCustomDates()" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600">
                    @foreach($periodLabels as $value => $label)
                        <option value="{{ $value }}" @selected($filters['period'] === $value)>{{ $label }}</option>
                    @endforeach
                </select>
            </div>
            <div id="customDates" class="md:col-span-2 grid grid-cols-2 gap-3 {{ $filters['period'] === 'custom' ? '' : 'hidden' }}">
                <div>
                    <label for="from" class="block text-sm font-medium text-gray-700 mb-1">Dari</label>
                    <input type="date" id="from" name="from" value="{{ $filters['period'] === 'custom' ? request('from') : '' }}" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600">
                </div>
                <div>
                    <label for="to" class="block text-sm font-medium text-gray-700 mb-1">Sampai</label>
                    <input type="date" id="to" name="to" value="{{ $filters['period'] === 'custom' ? request('to') : '' }}" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600">
                </div>
            </div>
            <button type="submit" class="px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm font-medium hover:bg-emerald-800">Tampilkan</button>
        </form>
    </div>

    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
            <p class="text-sm text-gray-500">Periode {{ $filters['from'] }} sampai {{ $filters['to'] }}</p>
            <p class="text-2xl font-bold text-gray-900">{{ number_format($tickets->total(), 0, ',', '.') }} pekerjaan selesai</p>
        </div>
        <div class="flex gap-2">
            <a href="{{ route('reports.excel', request()->query()) }}" class="px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm font-medium hover:bg-emerald-800">Download Excel</a>
        </div>
    </div>

    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
                <thead class="bg-gray-50 text-gray-700 uppercase text-xs font-semibold">
                    <tr>
                        <th class="px-5 py-4">Nomor Tiket</th>
                        <th class="px-5 py-4">Permintaan</th>
                        <th class="px-5 py-4">Kategori</th>
                        <th class="px-5 py-4">Pemohon</th>
                        <th class="px-5 py-4">Teknisi</th>
                        <th class="px-5 py-4">Selesai</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                    @forelse($tickets as $ticket)
                        <tr class="hover:bg-gray-50">
                            <td class="px-5 py-4 font-mono text-emerald-700 whitespace-nowrap">{{ $ticket->ticket_number }}</td>
                            <td class="px-5 py-4 font-medium text-gray-900 min-w-[220px]">{{ $ticket->subject }}</td>
                            <td class="px-5 py-4 text-gray-600 whitespace-nowrap">{{ $ticket->category?->name ?? '-' }}</td>
                            <td class="px-5 py-4 text-gray-600 whitespace-nowrap">{{ $ticket->creator?->name ?? '-' }}</td>
                            <td class="px-5 py-4 text-gray-600 whitespace-nowrap">{{ $ticket->technician?->name ?? '-' }}</td>
                            <td class="px-5 py-4 text-gray-600 whitespace-nowrap">{{ $ticket->resolved_at?->format('d M Y H:i') ?? '-' }}</td>
                        </tr>
                    @empty
                        <tr><td colspan="7" class="px-5 py-12 text-center text-gray-400">Tidak ada pekerjaan selesai pada periode ini.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
        @if($tickets->hasPages())
            <div class="px-5 py-4 border-t border-gray-200">{{ $tickets->links() }}</div>
        @endif
    </div>
</div>
@endsection

@push('scripts')
<script>
    function toggleCustomDates() {
        const customDates = document.getElementById('customDates');
        const isCustom = document.getElementById('period').value === 'custom';
        customDates.classList.toggle('hidden', !isCustom);
        document.getElementById('from').required = isCustom;
        document.getElementById('to').required = isCustom;
    }
</script>
@endpush