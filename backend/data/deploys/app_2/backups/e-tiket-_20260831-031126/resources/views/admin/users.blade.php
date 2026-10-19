@extends('layouts.app')

@section('title', 'Manajemen Pengguna')
@section('page-title', 'Manajemen Pengguna')
@section('page-subtitle', 'Kelola akun admin, teknisi, dan kepala divisi')

@section('content')
<div class="space-y-6">

    <div class="bg-white rounded-xl border border-gray-200 overflow-hidden fade-in">
        <div class="px-6 py-5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
                <h3 class="text-lg font-bold text-gray-900">Daftar Pengguna</h3>
                <p class="text-sm text-gray-500">Total {{ $users->total() }} pengguna terdaftar</p>
            </div>
            <button onclick="openCreateModal()" class="px-4 py-2 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 flex items-center gap-2 whitespace-nowrap self-start sm:self-auto">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                Tambah Pengguna
            </button>
        </div>

        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm">
                <thead class="bg-gray-50 text-gray-700 uppercase text-xs font-semibold">
                    <tr>
                        <th class="px-6 py-4">Nama</th>
                        <th class="px-6 py-4">Email</th>
                        <th class="px-6 py-4">Role</th>
                        <th class="px-6 py-4">Divisi</th>
                        <th class="px-6 py-4">Telepon</th>
                        <th class="px-6 py-4">Status</th>
                        <th class="px-6 py-4 text-right">Aksi</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-gray-100">
                    @forelse($users as $user)
                        <tr class="hover:bg-gray-50 transition-colors">
                            <td class="px-6 py-4">
                                <div class="flex items-center gap-3">
                                    <div class="w-8 h-8 bg-gradient-to-br from-emerald-600 to-emerald-800 text-white rounded-full flex items-center justify-center font-bold text-xs shrink-0">{{ strtoupper(substr($user->name, 0, 1)) }}</div>
                                    <span class="font-medium text-gray-900">{{ $user->name }}</span>
                                </div>
                            </td>
                            <td class="px-6 py-4 text-gray-600">{{ $user->email }}</td>
                            <td class="px-6 py-4">
                                @if($user->isAdmin())
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-100 whitespace-nowrap">Admin</span>
                                @elseif($user->isTechnician())
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-sky-50 text-sky-700 border border-sky-100 whitespace-nowrap">Teknisi</span>
                                @else
                                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-100 whitespace-nowrap">Ka. Divisi</span>
                                @endif
                            </td>
                            <td class="px-6 py-4 text-gray-600 whitespace-nowrap">{{ $user->division?->code ?? '-' }}</td>
                            <td class="px-6 py-4 text-gray-600 whitespace-nowrap">{{ $user->phone ?? '-' }}</td>
                            <td class="px-6 py-4">
                                @if($user->is_active)
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Aktif</span>
                                @else
                                    <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600 border border-gray-200 whitespace-nowrap"><span class="w-1.5 h-1.5 rounded-full bg-gray-400"></span>Nonaktif</span>
                                @endif
                            </td>
                            <td class="px-6 py-4 text-right whitespace-nowrap">
                                <button type="button" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline mr-3" data-edit-user="{{ $user->id }}">Edit</button>
                                @if(auth()->id() !== $user->id)
                                    <form action="{{ route('admin.users.toggle', $user) }}" method="POST" class="inline" onsubmit="return confirm('Yakin ingin mengubah status akun ini?')">
                                        @csrf
                                        <button type="submit" class="{{ $user->is_active ? 'text-rose-600 hover:text-rose-800' : 'text-emerald-700 hover:text-emerald-900' }} font-medium text-xs hover:underline">
                                            {{ $user->is_active ? 'Nonaktifkan' : 'Aktifkan' }}
                                        </button>
                                    </form>
                                    <form action="{{ route('admin.users.destroy', $user) }}" method="POST" class="inline ml-3" onsubmit="return confirm('Yakin ingin menghapus pengguna ini? Data yang sudah dihapus tidak dapat dikembalikan.')">
                                        @csrf
                                        @method('DELETE')
                                        <button type="submit" class="text-rose-600 hover:text-rose-800 font-medium text-xs hover:underline">Hapus</button>
                                    </form>
                                @endif
                            </td>
                        </tr>
                    @empty
                        <tr><td colspan="7" class="px-6 py-12 text-center text-gray-400">Belum ada pengguna.</td></tr>
                    @endforelse
                </tbody>
            </table>
        </div>
        @if($users->hasPages())
            <div class="px-6 py-4 border-t border-gray-200">
                {{ $users->links() }}
            </div>
        @endif
    </div>

</div>

<!-- Modal Buat Pengguna -->
<div id="createModal" class="fixed inset-0 z-50 hidden">
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="closeCreateModal()"></div>
    <div id="createModalContent" class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-2xl w-[calc(100%-2rem)] max-w-lg p-6 transform transition-all scale-95 opacity-0 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold text-gray-900">Tambah Pengguna</h3>
            <button onclick="closeCreateModal()" class="text-gray-400 hover:text-gray-600">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
        </div>
        <form action="{{ route('admin.users.store') }}" method="POST" class="space-y-4 text-sm">
            @csrf
            @include('admin.partials.user-fields')
            <div class="pt-2 flex justify-end gap-3">
                <button type="button" onclick="closeCreateModal()" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">Batal</button>
                <button type="submit" class="px-5 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-colors font-medium">Simpan</button>
            </div>
        </form>
    </div>
</div>

<!-- Modal Edit Pengguna -->
<div id="editModal" class="fixed inset-0 z-50 hidden">
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="closeEditModal()"></div>
    <div id="editModalContent" class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-2xl w-[calc(100%-2rem)] max-w-lg p-6 transform transition-all scale-95 opacity-0 max-h-[90vh] overflow-y-auto">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold text-gray-900">Edit Pengguna</h3>
            <button onclick="closeEditModal()" class="text-gray-400 hover:text-gray-600">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
        </div>
        <form id="editForm" method="POST" class="space-y-4 text-sm">
            @csrf
            @method('PUT')
            @include('admin.partials.user-fields', ['editing' => true])
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
    $usersById = collect($users->items())->mapWithKeys(fn (\App\Models\User $u) => [
        $u->id => ['id' => $u->id, 'name' => $u->name, 'email' => $u->email, 'role' => $u->role, 'division_id' => $u->division_id, 'phone' => $u->phone],
    ]);
?>
<script>
    const usersById = @json($usersById);

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

    function openEditModal(user) {
        const form = document.getElementById('editForm');
        form.action = @js(url('admin/users')) + '/' + user.id;
        document.getElementById('edit-name').value = user.name;
        document.getElementById('edit-email').value = user.email;
        document.getElementById('edit-password').value = '';
        document.getElementById('edit-role').value = user.role;
        document.getElementById('edit-division_id').value = user.division_id ?? '';
        document.getElementById('edit-phone').value = user.phone ?? '';
        toggleDivisionField('edit-role', 'edit-division-wrapper');
        openModal('editModal', 'editModalContent');
    }

    function toggleDivisionField(roleSelectId, wrapperId) {
        const role = document.getElementById(roleSelectId).value;
        document.getElementById(wrapperId).classList.toggle('hidden', role !== 'kepala_divisi');
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') { closeCreateModal(); closeEditModal(); }
    });

    document.querySelectorAll('[data-edit-user]').forEach((button) => {
        button.addEventListener('click', () => openEditModal(usersById[button.dataset.editUser]));
    });
</script>
@endpush
