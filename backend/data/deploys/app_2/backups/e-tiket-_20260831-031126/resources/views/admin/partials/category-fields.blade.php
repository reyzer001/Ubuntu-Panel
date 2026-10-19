@php $editing = $editing ?? false; @endphp

<div>
    <label for="{{ $editing ? 'edit' : '' }}-name" class="block text-gray-700 font-medium mb-1">Nama Kategori</label>
    <input type="text" name="name" id="{{ $editing ? 'edit' : '' }}-name" value="{{ old('name') }}" required placeholder="Contoh: Hardware (PC, Printer, Scanner)" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
    @error('name')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
</div>

<div class="grid grid-cols-2 gap-4">
    <div>
        <label for="{{ $editing ? 'edit' : '' }}-sla_response_minutes" class="block text-gray-700 font-medium mb-1">SLA Respons (menit)</label>
        <input type="number" name="sla_response_minutes" id="{{ $editing ? 'edit' : '' }}-sla_response_minutes" value="{{ old('sla_response_minutes', 60) }}" required min="1" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
        @error('sla_response_minutes')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
    </div>
    <div>
        <label for="{{ $editing ? 'edit' : '' }}-sla_resolve_minutes" class="block text-gray-700 font-medium mb-1">SLA Penyelesaian (menit)</label>
        <input type="number" name="sla_resolve_minutes" id="{{ $editing ? 'edit' : '' }}-sla_resolve_minutes" value="{{ old('sla_resolve_minutes', 240) }}" required min="1" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
        @error('sla_resolve_minutes')<p class="text-red-600 text-xs mt-1">{{ $message }}</p>@enderror
    </div>
</div>
