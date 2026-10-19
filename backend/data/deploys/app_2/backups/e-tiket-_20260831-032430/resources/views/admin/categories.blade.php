@extends('layouts.app')

@section('title', 'Kategori & SLA')
@section('page-title', 'Kategori & SLA')
@section('page-subtitle', 'Kelola kategori kendala dan target waktu layanan')

@section('content')
<div class="space-y-6">

    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden fade-in">
        <div class="px-6 py-5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
                <h3 class="text-lg font-bold text-gray-900">Daftar Kategori</h3>
                <p class="text-sm text-gray-500">SLA menentukan target waktu respons dan penyelesaian tiket</p>
            </div>
            <button onclick="openCreateModal()" class="px-4 py-2 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 flex items-center gap-2 whitespace-nowrap self-start sm:self-auto">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                Tambah Kategori
            </button>
        </div>

        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
                <thead class="bg-gray-50 text-gray-700 uppercase text-xs font-semibold">
                    <tr>
                        <th class="px-6 py-4">Nama Kategori</th>
                        <th class="px-6 py-4">SLA Respons</th>
                        <th class="px-6 py-4">SLA Penyelesaian</th>
                        <th class="px-6 py-4 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                    @forelse($categories as $category)
                        <tr class="hover:bg-gray-50 transition-colors">
                            <td class="px-6 py-4 font-medium text-gray-900">{{ $category->name }}</td>
                            <td class="px-6 py-4 text-gray-600 whitespace-nowrap">{{ $category->sla_response_minutes }} menit</td>
                            <td class="px-6 py-4 text-gray-600 whitespace-nowrap">{{ $category->sla_resolve_minutes }} menit</td>
                            <td class="px-6 py-4 text-right whitespace-nowrap">
                                <button type="button" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline mr-3" data-edit-category="{{ $category->id }}">Edit</button>
                                <form action="{{ route('admin.categories.destroy', $category) }}" method="POST" class="inline" onsubmit="return confirm('Yakin ingin menghapus kategori ini?')">
                                    @csrf
                                    @method('DELETE')
                                    <button type="submit" class="text-rose-600 hover:text-rose-800 font-medium text-xs hover:underline">Hapus</button>
                                </form>
                            </td>
                        </tr>
                    @empty
                        <tr><td colspan="4" class="px-6 py-12 text-center text-gray-400">Belum ada kategori.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
    </div>

</div>

<!-- Modal Buat Kategori -->
<div id="createModal" class="fixed inset-0 z-50 hidden">
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="closeCreateModal()"></div>
    <div id="createModalContent" class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-2xl w-[calc(100%-2rem)] max-w-lg p-6 transform transition-all scale-95 opacity-0">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold text-gray-900">Tambah Kategori</h3>
            <button onclick="closeCreateModal()" class="text-gray-400 hover:text-gray-600">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
        </div>
        <form action="{{ route('admin.categories.store') }}" method="POST" class="space-y-4 text-sm">
            @csrf
            @include('admin.partials.category-fields')
            <div class="pt-2 flex justify-end gap-3">
                <button type="button" onclick="closeCreateModal()" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">Batal</button>
                <button type="submit" class="px-5 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-colors font-medium">Simpan</button>
            </div>
        </form>
    </div>
</div>

<!-- Modal Edit Kategori -->
<div id="editModal" class="fixed inset-0 z-50 hidden">
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="closeEditModal()"></div>
    <div id="editModalContent" class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-2xl w-[calc(100%-2rem)] max-w-lg p-6 transform transition-all scale-95 opacity-0">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold text-gray-900">Edit Kategori</h3>
            <button onclick="closeEditModal()" class="text-gray-400 hover:text-gray-600">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
        </div>
        <form id="editForm" method="POST" class="space-y-4 text-sm">
            @csrf
            @method('PUT')
            @include('admin.partials.category-fields', ['editing' => true])
            <div class="pt-2 flex justify-end gap-3">
                <button type="button" onclick="closeEditModal()" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">Batal</button>
                <button type="submit" class="px-5 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-colors font-medium">Simpan Perubahan</button>
            </div>
        </form>
    </div>
</div>
@endsection

@push('scripts')
<?php
    $categoriesById = $categories->mapWithKeys(fn (\App\Models\Category $c) => [
        $c->id => ['id' => $c->id, 'name' => $c->name, 'sla_response_minutes' => $c->sla_response_minutes, 'sla_resolve_minutes' => $c->sla_resolve_minutes],
    ]);
?>
<script>
    const categoriesById = @json($categoriesById);

    function openModal(modalId, contentId) {
        const modal = document.getElementById(modalId);
        const content = document.getElementById(contentId);
        modal.classList.remove('hidden');
        setTimeout(() => {
            content.classList.remove('scale-95', 'opacity-0');
            content.classList.add('scale-100', 'opacity-100');
        }, 10);
    }

    function closeModal(modalId, contentId) {
        const modal = document.getElementById(modalId);
        const content = document.getElementById(contentId);
        content.classList.remove('scale-100', 'opacity-100');
        content.classList.add('scale-95', 'opacity-0');
        setTimeout(() => modal.classList.add('hidden'), 200);
    }

    function openCreateModal() { openModal('createModal', 'createModalContent'); }
    function closeCreateModal() { closeModal('createModal', 'createModalContent'); }
    function closeEditModal() { closeModal('editModal', 'editModalContent'); }

    function openEditModal(category) {
        const form = document.getElementById('editForm');
        form.action = @js(url('admin/categories')) + '/' + category.id;
        document.getElementById('edit-name').value = category.name;
        document.getElementById('edit-sla_response_minutes').value = category.sla_response_minutes;
        document.getElementById('edit-sla_resolve_minutes').value = category.sla_resolve_minutes;
        openModal('editModal', 'editModalContent');
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { closeCreateModal(); closeEditModal(); }
    });

    document.querySelectorAll('[data-edit-category]').forEach((button) => {
        button.addEventListener('click', () => openEditModal(categoriesById[button.dataset.editCategory]));
    });
</script>
@endpush
