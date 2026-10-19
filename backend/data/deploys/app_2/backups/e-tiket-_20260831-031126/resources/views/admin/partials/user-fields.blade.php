@php $editing = $editing ?? false; @endphp

<div>
    <label for="{{ $editing ? 'edit' : '' }}-name" class="block text-gray-700 font-medium mb-1">Nama Lengkap</label>
    <input type="text" name="name" id="{{ $editing ? 'edit' : '' }}-name" value="{{ old('name', $editing ? '' : '') }}" required placeholder="Nama lengkap pengguna" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
    @error('name')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
</div>

<div>
    <label for="{{ $editing ? 'edit' : '' }}-email" class="block text-gray-700 font-medium mb-1">Email</label>
    <input type="email" name="email" id="{{ $editing ? 'edit' : '' }}-email" value="{{ old('email') }}" required placeholder="email@rsefarina.co.id" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
    @error('email')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
</div>

<div>
    <label for="{{ $editing ? 'edit' : '' }}-password" class="block text-gray-700 font-medium mb-1">Password @if($editing)<span class="text-gray-400 font-normal">(kosongkan jika tidak diubah)</span>@endif</label>
    <input type="password" name="password" id="{{ $editing ? 'edit' : '' }}-password" @unless($editing) required @endunless minlength="8" placeholder="Minimal 8 karakter" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
    @error('password')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
</div>

<div class="grid grid-cols-2 gap-4">
    <div>
        <label for="{{ $editing ? 'edit' : '' }}-role" class="block text-gray-700 font-medium mb-1">Role</label>
        <select name="role" id="{{ $editing ? 'edit' : '' }}-role" required onchange="toggleDivisionField('{{ $editing ? 'edit' : '' }}-role', '{{ $editing ? 'edit' : '' }}-division-wrapper')" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer transition-colors hover:border-gray-400">
            <option value="">Pilih Role</option>
            <option value="admin">Admin (Kepala IT)</option>
            <option value="teknisi">Teknisi IT</option>
            <option value="kepala_divisi">Kepala Divisi</option>
        </select>
        @error('role')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
    </div>
    <div id="{{ $editing ? 'edit' : '' }}-division-wrapper" class="{{ ! $editing && old('role') === 'kepala_divisi' ? '' : 'hidden' }}">
        <label for="{{ $editing ? 'edit' : '' }}-division_id" class="block text-gray-700 font-medium mb-1">Divisi</label>
        <select name="division_id" id="{{ $editing ? 'edit' : '' }}-division_id" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer transition-colors hover:border-gray-400">
            <option value="">Pilih Divisi</option>
            @foreach($divisions as $division)
                <option value="{{ $division->id }}">{{ $division->name }}</option>
            @endforeach
        </select>
        @error('division_id')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
    </div>
</div>

<div>
    <label for="{{ $editing ? 'edit' : '' }}-phone" class="block text-gray-700 font-medium mb-1">Nomor Telepon <span class="text-gray-400 font-normal">(opsional)</span></label>
    <input type="tel" name="phone" id="{{ $editing ? 'edit' : '' }}-phone" value="{{ old('phone') }}" placeholder="08xxxxxxxxxx" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
    @error('phone')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
</div>
