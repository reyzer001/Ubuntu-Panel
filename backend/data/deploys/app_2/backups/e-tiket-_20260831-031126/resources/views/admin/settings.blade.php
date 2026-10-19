@extends('layouts.app')

@section('title', 'Pengaturan')
@section('page-title', 'Pengaturan')
@section('page-subtitle', 'Kelola profil perusahaan yang tampil di aplikasi dan laporan')

@section('content')
<div class="space-y-6 max-w-3xl">

    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden fade-in">
        <div class="px-6 py-5 border-b border-gray-200">
            <h3 class="text-lg font-bold text-gray-900">Logo Perusahaan</h3>
            <p class="text-sm text-gray-500 mt-0.5">Logo tampil di sidebar, halaman login, dan kop file Excel rekap pekerjaan. Logo aktif tetap dipakai sampai Anda menggantinya.</p>
        </div>

        <form action="{{ route('admin.settings.update') }}" method="POST" enctype="multipart/form-data" class="p-6 space-y-6">
            @csrf

            <div class="flex flex-col sm:flex-row sm:items-center gap-6">
                <div class="shrink-0">
                    <p class="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Logo Saat Ini</p>
                    <div class="w-28 h-28 rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 flex items-center justify-center overflow-hidden">
                        @if($companyLogoUrl)
                            <img src="{{ $companyLogoUrl }}" alt="Logo perusahaan" class="w-full h-full object-contain p-1.5">
                        @else
                            <span class="text-gray-400 text-xs text-center px-2">Belum ada logo</span>
                        @endif
                    </div>
                </div>

                <div class="flex-1 w-full">
                    <label for="logo" class="block text-sm font-medium text-gray-700 mb-1">Ganti Logo</label>
                    <input type="file" name="logo" id="logo" accept=".jpg,.jpeg,.png" required
                        class="w-full text-sm text-gray-600 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-emerald-50 file:text-emerald-700 file:font-medium hover:file:bg-emerald-100 file:cursor-pointer file:transition-colors border border-gray-300 rounded-lg cursor-pointer focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none">
                    <p class="text-xs text-gray-400 mt-2">Format JPG atau PNG, ukuran maksimal 2 MB. Disarankan gambar persegi agar rapi saat ditampilkan.</p>
                    @error('logo')
                        <p class="text-rose-600 text-xs mt-1 font-medium">{{ $message }}</p>
                    @enderror
                </div>
            </div>

            <div class="pt-2 border-t border-gray-100 flex justify-end">
                <button type="submit" class="px-5 py-2.5 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800 active:scale-[0.99] transition-all shadow-md shadow-emerald-700/20 cursor-pointer">
                    Simpan Logo
                </button>
            </div>
        </form>
    </div>

</div>
@endsection
