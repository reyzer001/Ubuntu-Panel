@extends('layouts.app')

@section('title', 'Detail ' . $ticket->ticket_number)
@section('page-title', 'Detail Tiket')
@section('page-subtitle', $ticket->ticket_number)

@section('content')
<div class="max-w-5xl mx-auto space-y-6">

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">

        <!-- Left: Ticket Info -->
        <div class="lg:col-span-2 space-y-6">

            <!-- Detail Card -->
            <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in">
                <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 pb-4 border-b border-gray-100">
                    <h3 class="text-lg font-bold text-gray-900 font-mono text-emerald-700">{{ $ticket->ticket_number }}</h3>
                    <div class="flex items-center gap-2">
                        @if($ticket->status === 'open')
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>Open</span>
                        @elseif($ticket->status === 'assigned')
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-sky-50 text-sky-700 border border-sky-200"><span class="w-1.5 h-1.5 rounded-full bg-sky-500"></span>Assigned</span>
                        @elseif($ticket->status === 'in_progress')
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-700 animate-pulse"></span>In Progress</span>
                        @elseif($ticket->status === 'pending')
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-50 text-yellow-700 border border-yellow-200"><span class="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>Pending</span>
                        @elseif($ticket->status === 'resolved')
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200"><span class="w-1.5 h-1.5 rounded-full bg-teal-500"></span>Resolved</span>
                        @else
                            <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Closed</span>
                        @endif

                        @if($ticket->priority === 'emergency')
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-800 border border-red-200">Emergency</span>
                        @elseif($ticket->priority === 'high')
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-100">High</span>
                        @elseif($ticket->priority === 'medium')
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-50 text-orange-700 border border-orange-100">Medium</span>
                        @else
                            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-100">Low</span>
                        @endif
                    </div>
                </div>

                <p class="text-base font-semibold text-gray-900 mb-4">{{ $ticket->subject }}</p>

                <div class="grid grid-cols-2 gap-4 text-sm">
                    <div><p class="text-gray-500 text-xs uppercase font-semibold">Kategori</p><p class="font-medium text-gray-900 mt-0.5">{{ $ticket->category->name }}</p></div>
                    <div><p class="text-gray-500 text-xs uppercase font-semibold">Divisi</p><p class="font-medium text-gray-900 mt-0.5">{{ $ticket->division->name }}</p></div>
                    <div><p class="text-gray-500 text-xs uppercase font-semibold">Pengaju</p><p class="font-medium text-gray-900 mt-0.5">{{ $ticket->creator->name ?? '-' }}</p></div>
                    <div><p class="text-gray-500 text-xs uppercase font-semibold">Petugas</p><p class="font-medium text-gray-900 mt-0.5">{{ $ticket->technician->name ?? 'Belum ditugaskan' }}</p></div>
                    <div><p class="text-gray-500 text-xs uppercase font-semibold">Lokasi</p><p class="font-medium text-gray-900 mt-0.5">{{ $ticket->location }}</p></div>
                    <div><p class="text-gray-500 text-xs uppercase font-semibold">Kode Aset</p><p class="font-medium text-gray-900 mt-0.5">{{ $ticket->asset_code ?? '-' }}</p></div>
                    <div><p class="text-gray-500 text-xs uppercase font-semibold">Dibuat</p><p class="font-medium text-gray-900 mt-0.5">{{ $ticket->created_at->translatedFormat('d F Y, H:i') }} WIB</p></div>
                    <div>
                        <p class="text-gray-500 text-xs uppercase font-semibold">SLA Penyelesaian</p>
                        <p class="font-medium mt-0.5 {{ $ticket->created_at->diffInMinutes(now()) > $ticket->category->sla_resolve_minutes && !in_array($ticket->status, ['resolved', 'closed']) ? 'text-red-600' : 'text-gray-900' }}">
                            {{ $ticket->category->sla_resolve_minutes }} menit
                            @if($ticket->created_at->diffInMinutes(now()) > $ticket->category->sla_resolve_minutes && !in_array($ticket->status, ['resolved', 'closed']))
                                (Terlampaui)
                            @endif
                        </p>
                    </div>
                </div>

                <div class="mt-5 p-3 bg-gray-50 rounded-lg">
                    <p class="text-gray-500 text-xs uppercase font-semibold mb-1">Deskripsi Kendala</p>
                    <p class="text-gray-700 whitespace-pre-line">{{ $ticket->description }}</p>
                </div>
            </div>

            <!-- Riwayat Penanganan -->
            <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.1s">
                <h3 class="text-lg font-bold text-gray-900 mb-4">Riwayat Penanganan</h3>
                <div class="space-y-4">
                    @forelse($ticket->logs as $log)
                        <div class="flex gap-3 items-start">
                            <div class="flex flex-col items-center">
                                <span class="w-2.5 h-2.5 rounded-full bg-emerald-600 mt-1.5"></span>
                                <span class="w-px h-full bg-gray-200 mt-1"></span>
                            </div>
                            <div class="pb-1 min-w-0">
                                <p class="text-sm font-semibold text-gray-900">{{ $log->action }} <span class="font-normal text-gray-400">&middot; {{ $log->user->name ?? 'Sistem' }}</span></p>
                                <p class="text-sm text-gray-600 mt-0.5 break-words">{{ $log->note }}</p>
                                <p class="text-xs text-gray-400 mt-1">{{ $log->created_at->translatedFormat('d M Y, H:i') }} WIB</p>
                            </div>
                        </div>
                    @empty
                        <p class="text-sm text-gray-400">Belum ada riwayat.</p>
                    @endforelse
                </div>
            </div>

        </div>

        <!-- Right: Actions -->
        <div class="space-y-6">

            @can('assign', $ticket)
                @if(in_array($ticket->status, ['open', 'assigned']))
                    <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in">
                        <h3 class="font-bold text-gray-900 mb-1">Penugasan Teknisi</h3>
                        <p class="text-sm text-gray-500 mb-4">Pilih teknisi IT untuk menangani tiket ini.</p>
                        <form action="{{ route('tickets.assign', $ticket) }}" method="POST" class="space-y-3 text-sm">
                            @csrf
                            <select name="technician_id" required class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer transition-colors hover:border-gray-400">
                                <option value="">Pilih Teknisi</option>
                                @foreach($technicians as $technician)
                                    <option value="{{ $technician->id }}" @selected($ticket->technician_id === $technician->id)>{{ $technician->name }}</option>
                                @endforeach
                            </select>
                            <button type="submit" class="w-full px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 font-medium">Tugaskan</button>
                        </form>
                    </div>
                @endif
            @endcan

            @can('respond', $ticket)
                @if(in_array($ticket->status, ['assigned', 'in_progress', 'pending']))
                    <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in">
                        <h3 class="font-bold text-gray-900 mb-1">Aksi Penanganan</h3>
                        <p class="text-sm text-gray-500 mb-4">Perbarui progres pengerjaan tiket.</p>

                        <div class="space-y-3 text-sm">
                            @if($ticket->status === 'assigned')
                                <form action="{{ route('tickets.status', $ticket) }}" method="POST">
                                    @csrf
                                    @method('PATCH')
                                    <input type="hidden" name="status" value="in_progress">
                                    <button type="submit" class="w-full px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 font-medium flex items-center justify-center gap-2">
                                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                                        Mulai Kerjakan
                                    </button>
                                </form>
                            @endif

                            <form action="{{ route('tickets.status', $ticket) }}" method="POST" class="space-y-2">
                                @csrf
                                @method('PATCH')
                                <input type="hidden" name="status" value="pending">
                                <textarea name="note" rows="2" required placeholder="Alasan penundaan (wajib)..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400"></textarea>
                                <button type="submit" class="w-full px-4 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 transition-colors font-medium">Tunda Pekerjaan</button>
                            </form>

                            <form action="{{ route('tickets.status', $ticket) }}" method="POST" class="space-y-2">
                                @csrf
                                @method('PATCH')
                                <input type="hidden" name="status" value="resolved">
                                <textarea name="note" rows="2" required placeholder="Solusi / tindakan yang dilakukan (wajib)..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400"></textarea>
                                <button type="submit" class="w-full px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors font-medium">Selesaikan (Resolved)</button>
                            </form>
                        </div>
                    </div>
                @endif
            @endcan

            @can('close', $ticket)
                @if($ticket->status === 'resolved')
                    <div class="bg-white rounded-xl border border-teal-200 p-6 fade-in ring-1 ring-teal-100">
                        <h3 class="font-bold text-gray-900 mb-1">Konfirmasi Penyelesaian</h3>
                        <p class="text-sm text-gray-500 mb-4">Masalah sudah teratasi? Konfirmasikan untuk menutup tiket.</p>
                        <form action="{{ route('tickets.close', $ticket) }}" method="POST" class="space-y-3 text-sm">
                            @csrf
                            @method('PATCH')
                            <button type="submit" class="w-full px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 font-medium">Tutup Tiket</button>
                        </form>
                    </div>
                @elseif($ticket->status === 'closed')
                    <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in">
                        <h3 class="font-bold text-gray-900 mb-1">Buka Kembali Tiket</h3>
                        <p class="text-sm text-gray-500 mb-4">Masalah terulang? Buka kembali tiket dengan menyertakan alasan.</p>
                        <form action="{{ route('tickets.reopen', $ticket) }}" method="POST" class="space-y-3 text-sm">
                            @csrf
                            @method('PATCH')
                            <textarea name="note" rows="2" required placeholder="Alasan pembukaan kembali..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400"></textarea>
                            <button type="submit" class="w-full px-4 py-2 border border-amber-300 bg-amber-50 text-amber-800 rounded-lg hover:bg-amber-100 transition-colors font-medium">Buka Kembali (Reopen)</button>
                        </form>
                    </div>
                @endif
            @endcan

            <a href="{{ route('tickets.index') }}" class="block text-center px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors text-sm font-medium bg-white">
                Kembali ke Daftar Tiket
            </a>
        </div>
    </div>

</div>
@endsection
