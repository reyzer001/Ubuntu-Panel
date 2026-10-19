<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Masuk - E-Tiket Report RS Efarina Etaham</title>

    <!-- Vite Assets -->
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="min-h-screen bg-gray-50 text-gray-800">

    <div class="flex min-h-screen">

        <!-- Left Side: Brand Panel -->
        <div class="hidden lg:flex lg:w-[45%] bg-emerald-950 text-white flex-col justify-between p-10 xl:p-14 relative overflow-hidden bg-cover bg-center" style="background-image: linear-gradient(rgba(0, 51, 42, 0.68), rgba(0, 35, 30, 0.8)), url('{{ asset('images/Efarina.png') }}');">
            <div class="absolute inset-0 bg-emerald-950/10"></div>

            <div class="relative">
                <div class="flex items-center gap-3">
                    @if($companyLogoUrl = \App\Models\Setting::companyLogoUrl())
                        <img src="{{ $companyLogoUrl }}" alt="Logo" class="w-12 h-12 rounded-lg object-contain bg-white p-0.5 shadow-lg">
                    @else
                        <div class="w-12 h-12 bg-emerald-600 rounded-lg flex items-center justify-center font-bold text-2xl shadow-lg shadow-emerald-600/30">E</div>
                    @endif
                    <div>
                        <h1 class="text-xl font-bold leading-tight">E-Tiket Report</h1>
                        <p class="text-xs text-emerald-300">RS Efarina Etaham Karawang</p>
                    </div>
                </div>
            </div>

            <div class="relative space-y-6 fade-in">
                <h2 class="text-3xl font-bold leading-snug">Solusi Cepat Permasalahan IT Rumah Sakit</h2>
                <p class="text-sm text-emerald-200/80 leading-relaxed max-w-md">Sistem tiket terpadu untuk koordinasi instan antara unit ruangan/divisi, staf teknisi IT lapangan, dan Kepala Unit IT demi kelancaran pelayanan klinis rumah sakit.</p>

                <ul class="space-y-3 text-sm text-emerald-100 pt-2">
                    <li class="flex items-center gap-3">
                        <span class="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600/40 shrink-0">
                            <svg class="w-3 h-3 text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
                        </span>
                        Respons cepat &amp; pemantauan SLA real-time
                    </li>
                    <li class="flex items-center gap-3">
                        <span class="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600/40 shrink-0">
                            <svg class="w-3 h-3 text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
                        </span>
                        Prioritas emergency untuk unit kritis (IGD, ICU, OK)
                    </li>
                    <li class="flex items-center gap-3">
                        <span class="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600/40 shrink-0">
                            <svg class="w-3 h-3 text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
                        </span>
                        Riwayat &amp; log solusi perbaikan terarsip lengkap
                    </li>
                </ul>
            </div>

            <div class="relative bg-emerald-900/50 rounded-lg p-4 border border-emerald-800 max-w-xs">
                <p class="text-xs text-emerald-300 mb-1">Versi Sistem</p>
                <p class="text-sm font-semibold">v1.0.0 (Waterfall)</p>
                <p class="text-xs text-emerald-400 mt-1">Laravel + SQLite</p>
            </div>
        </div>

        <!-- Right Side: Form Login -->
        <div class="flex-1 flex flex-col items-center justify-center p-6 sm:p-10">

            <!-- Brand mobile -->
            <div class="lg:hidden flex items-center gap-3 mb-8 fade-in">
                @if($companyLogoUrl = \App\Models\Setting::companyLogoUrl())
                    <img src="{{ $companyLogoUrl }}" alt="Logo" class="w-11 h-11 rounded-lg object-contain bg-white border border-gray-200 p-0.5 shadow-sm">
                @else
                    <div class="w-11 h-11 bg-emerald-600 rounded-lg flex items-center justify-center font-bold text-xl shadow-lg shadow-emerald-600/30 text-white">E</div>
                @endif
                <div>
                    <h1 class="text-lg font-bold leading-tight text-gray-900">E-Tiket Report</h1>
                    <p class="text-xs text-gray-500">RS Efarina Etaham Karawang</p>
                </div>
            </div>

            <div class="w-full max-w-md space-y-6">

                <!-- Kartu Login -->
                <div class="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 shadow-sm fade-in">
                    <div class="mb-6">
                        <h2 class="text-xl font-bold text-gray-900">Selamat Datang</h2>
                        <p class="text-sm text-gray-500 mt-1">Silakan masuk menggunakan email dan password akun Anda.</p>
                    </div>

                    @if(session('error'))
                        <div class="mb-4 p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs rounded-lg flex items-start gap-2">
                            <svg class="w-4 h-4 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
                            <span>{{ session('error') }}</span>
                        </div>
                    @endif

                    <form action="{{ route('login.post') }}" method="POST" class="space-y-4 text-sm">
                        @csrf
                        <div>
                            <label for="email" class="block text-gray-700 font-medium mb-1">Alamat Email</label>
                            <input type="email" name="email" id="email" value="{{ old('email') }}" required autofocus placeholder="email@rsefarina.co.id" class="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
                            @error('email')
                                <p class="text-rose-600 text-xs mt-1 font-medium">{{ $message }}</p>
                            @enderror
                        </div>

                        <div>
                            <div class="flex items-center justify-between mb-1">
                                <label for="password" class="block text-gray-700 font-medium">Kata Sandi</label>
                                <button type="button" onclick="togglePassword()" id="toggleBtn" class="text-xs text-emerald-700 hover:text-emerald-900 font-medium">Lihat</button>
                            </div>
                            <input type="password" name="password" id="password" required placeholder="••••••••" class="w-full px-3 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none transition-colors hover:border-gray-400">
                            @error('password')
                                <p class="text-rose-600 text-xs mt-1 font-medium">{{ $message }}</p>
                            @enderror
                        </div>

                        <button type="submit" class="w-full py-2.5 bg-emerald-700 text-white font-medium rounded-lg hover:bg-emerald-800 active:scale-[0.99] transition-all shadow-md shadow-emerald-700/20 cursor-pointer">
                            Masuk
                        </button>
                    </form>
                </div>

                <p class="text-center text-xs text-gray-400">&copy; {{ date('Y') }} Sistem E-Tiket Report - RS Efarina Etaham Karawang</p>
            </div>
        </div>
    </div>

    <script>
        function togglePassword() {
            const input = document.getElementById('password');
            const btn = document.getElementById('toggleBtn');
            const isHidden = input.type === 'password';
            input.type = isHidden ? 'text' : 'password';
            btn.textContent = isHidden ? 'Sembunyikan' : 'Lihat';
        }
    </script>
</body>
</html>
