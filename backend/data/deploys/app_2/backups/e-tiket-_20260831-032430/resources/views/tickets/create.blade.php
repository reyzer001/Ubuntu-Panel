@extends('layouts.app')

@section('title', 'Buat Tiket Baru')
@section('page-title', 'Buat Tiket Baru')
@section('page-subtitle', 'Laporkan kendala IT unit Anda')

@section('content')
<div class="max-w-2xl mx-auto">
    <div class="bg-white rounded-xl border border-gray-200 p-6 md:p-8 fade-in">
        <div class="mb-6">
            <h3 class="text-lg font-bold text-gray-900">Formulir Pelaporan</h3>
            <p class="text-sm text-gray-500">Jelaskan kendala secara mendetail agar teknisi dapat merespons dengan cepat.</p>
        </div>

        <form action="{{ route('tickets.store') }}" method="POST" class="space-y-4 text-sm">
            @csrf
            <div>
                <label for="subject" class="block text-gray-700 font-medium mb-1">Judul / Keluhan <span class="text-red-500">*</span></label>
                <input type="text" name="subject" id="subject" value="{{ old('subject') }}" required placeholder="Contoh: Gangguan PC Poli Anak" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
                @error('subject')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label for="category_id" class="block text-gray-700 font-medium mb-1">Kategori <span class="text-red-500">*</span></label>
                    <select name="category_id" id="category_id" required class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer transition-colors hover:border-gray-400">
                        <option value="">Pilih Kategori</option>
                        @foreach($categories as $category)
                            <option value="{{ $category->id }}" @selected(old('category_id') == $category->id)>{{ $category->name }}</option>
                        @endforeach
                    </select>
                    @error('category_id')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label for="priority" class="block text-gray-700 font-medium mb-1">Prioritas <span class="text-red-500">*</span></label>
                    <select name="priority" id="priority" required class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer transition-colors hover:border-gray-400">
                        <option value="">Pilih Prioritas</option>
                        @foreach(['low' => 'Low - Tidak mendesak', 'medium' => 'Medium - Mengganggu operasional', 'high' => 'High - Operasional terhambat', 'emergency' => 'Emergency - Unit kritis terdampak'] as $value => $label)
                            <option value="{{ $value }}" @selected(old('priority') === $value)>{{ $label }}</option>
                        @endforeach
                    </select>
                    @error('priority')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
                </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                    <label for="location" class="block text-gray-700 font-medium mb-1">Lokasi / Ruangan <span class="text-red-500">*</span></label>
                    <input type="text" name="location" id="location" value="{{ old('location') }}" required placeholder="Contoh: Ruang Rawat Inap Lt. 3" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
                    @error('location')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
                </div>
                <div>
                    <label for="asset_code" class="block text-gray-700 font-medium mb-1">Kode Aset <span class="text-gray-400 font-normal">(opsional)</span></label>
                    <input type="text" name="asset_code" id="asset_code" value="{{ old('asset_code') }}" placeholder="Contoh: PC-RNP-012" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
                    @error('asset_code')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
                </div>
            </div>

            <div>
                <label for="description" class="block text-gray-700 font-medium mb-1">Deskripsi Kendala <span class="text-red-500">*</span></label>
                <textarea name="description" id="description" rows="5" required placeholder="Jelaskan kendala secara mendetail..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">{{ old('description') }}</textarea>
                @error('description')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
            </div>

            <div class="pt-2 flex justify-end gap-3">
                <a href="{{ route('tickets.index') }}" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">Batal</a>
                <button type="submit" class="px-5 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 font-medium">Simpan Tiket</button>
            </div>
        </form>
    </div>
</div>
@endsection
