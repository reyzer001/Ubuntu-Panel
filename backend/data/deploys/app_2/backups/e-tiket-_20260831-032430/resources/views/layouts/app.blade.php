<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>@yield('title', 'Dashboard E-Tiket Report') - RS Efarina Etaham</title>

    <!-- Vite Assets -->
    @vite(['resources/css/app.css', 'resources/js/app.js'])
</head>
<body class="bg-gray-50 text-gray-800">

    <!-- Mobile Overlay -->
    <div id="mobileOverlay" class="fixed inset-0 bg-black/50 z-30 hidden sm:hidden" onclick="toggleSidebar()"></div>

    <!-- Sidebar -->
    <aside id="sidebar" class="fixed top-0 left-0 z-40 w-64 h-screen transition-transform -translate-x-full sm:translate-x-0 bg-emerald-950 text-white sidebar-scroll overflow-y-auto">
        <div class="h-full px-4 py-6">
            <div class="flex items-center gap-3 mb-8 px-2">
                @if($companyLogoUrl = \App\Models\Setting::companyLogoUrl())
                    <img src="{{ $companyLogoUrl }}" alt="Logo" class="w-10 h-10 rounded-lg object-contain bg-white shadow-lg shadow-emerald-600/20 p-0.5">
                @else
                    <div class="w-10 h-10 bg-emerald-600 rounded-lg flex items-center justify-center font-bold text-xl shadow-lg shadow-emerald-600/30">E</div>
                @endif
                <div>
                    <h1 class="text-lg font-bold leading-tight">E-Tiket Report</h1>
                    <p class="text-xs text-emerald-300">RS Efarina Etaham</p>
                </div>
            </div>

            <nav class="space-y-1">
                <a href="{{ route('dashboard') }}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 {{ request()->routeIs('dashboard') ? 'bg-emerald-700 text-white font-medium shadow-md shadow-emerald-950/20' : 'text-emerald-200 hover:bg-emerald-900 hover:text-white' }}">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
                    Dashboard
                </a>
                <a href="{{ route('tickets.index') }}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 {{ request()->routeIs('tickets.*') ? 'bg-emerald-700 text-white font-medium shadow-md shadow-emerald-950/20' : 'text-emerald-200 hover:bg-emerald-900 hover:text-white' }}">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
                    Kelola Tiket
                </a>
                <a href="{{ route('reports.index') }}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 {{ request()->routeIs('reports.*') ? 'bg-emerald-700 text-white font-medium shadow-md shadow-emerald-950/20' : 'text-emerald-200 hover:bg-emerald-900 hover:text-white' }}">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2Z"/></svg>
                    Rekapan Pekerjaan
                </a>

                @if(Auth::user()->isDivisionHead())
                    <a href="{{ route('tickets.create') }}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 {{ request()->routeIs('tickets.create') ? 'bg-emerald-700 text-white font-medium shadow-md shadow-emerald-950/20' : 'text-emerald-200 hover:bg-emerald-900 hover:text-white' }}">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
                        Buat Tiket
                    </a>
                @endif

                @if(Auth::user()->isAdmin())
                    <p class="text-xs text-emerald-400 uppercase font-semibold pt-4 pb-1 px-3 tracking-wider">Administrasi</p>
                    <a href="{{ route('admin.users.index') }}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 {{ request()->routeIs('admin.users.*') ? 'bg-emerald-700 text-white font-medium shadow-md shadow-emerald-950/20' : 'text-emerald-200 hover:bg-emerald-900 hover:text-white' }}">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
                        Pengguna
                    </a>
                    <a href="{{ route('admin.categories.index') }}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 {{ request()->routeIs('admin.categories.*') ? 'bg-emerald-700 text-white font-medium shadow-md shadow-emerald-950/20' : 'text-emerald-200 hover:bg-emerald-900 hover:text-white' }}">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                        Kategori &amp; SLA
                    </a>
                    <a href="{{ route('admin.settings.edit') }}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 {{ request()->routeIs('admin.settings.*') ? 'bg-emerald-700 text-white font-medium shadow-md shadow-emerald-950/20' : 'text-emerald-200 hover:bg-emerald-900 hover:text-white' }}">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.5 1.5H8.25A2.25 2.25 0 006 3.75v16.5a2.25 2.25 0 002.25 2.25h7.5A2.25 2.25 0 0018 20.25V3.75a2.25 2.25 0 00-2.25-2.25H13.5m-3 0V3h3V1.5m-3 0h3m-3 18.75h3"/></svg>
                        Pengaturan
                    </a>
                @endif
            </nav>

            <div class="mt-8 pt-6 border-t border-emerald-900">
                <p class="text-xs text-emerald-400 uppercase font-semibold mb-3 px-3 tracking-wider">Status Sistem</p>
                <div class="px-3 space-y-3">
                    <div class="flex items-center justify-between text-sm">
                        <span class="text-emerald-300">Database</span>
                        <span class="flex items-center gap-1.5 text-emerald-400 font-medium">
                            <span class="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span>
                            Online
                        </span>
                    </div>
                    <div class="flex items-center justify-between text-sm">
                        <span class="text-emerald-300">Web Server</span>
                        <span class="flex items-center gap-1.5 text-emerald-400 font-medium">
                            <span class="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span>
                            Aktif
                        </span>
                    </div>
                </div>
            </div>

            <div class="mt-8 px-3">
                <div class="bg-emerald-900/50 rounded-lg p-4 border border-emerald-800">
                    <p class="text-xs text-emerald-300 mb-1">Masuk Sebagai</p>
                    <p class="text-sm font-semibold text-white truncate">{{ Auth::user()->name }}</p>
                    <p class="text-xs text-emerald-400 mt-0.5">
                        @if(Auth::user()->isAdmin()) Administrator
                        @elseif(Auth::user()->isTechnician()) Teknisi IT
                        @else Kepala Divisi{{ Auth::user()->division ? ' - ' . Auth::user()->division->code : '' }}
                        @endif
                    </p>
                </div>
            </div>

            <div class="mt-6 px-3">
                <form action="{{ route('logout') }}" method="POST">
                    @csrf
                    <button type="submit" class="w-full flex items-center justify-center gap-2 px-3 py-2.5 text-emerald-200 hover:bg-rose-500/10 hover:text-rose-400 border border-emerald-800 hover:border-rose-500/30 rounded-lg transition-all duration-200 cursor-pointer text-sm font-medium">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
                        Keluar
                    </button>
                </form>
            </div>
        </div>
    </aside>

    <!-- Main Content -->
    <div class="sm:ml-64 min-h-screen flex flex-col">
        <!-- Top Header -->
        <header class="bg-white border-b border-gray-200 sticky top-0 z-20 px-6 py-4">
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-4">
                    <button onclick="toggleSidebar()" class="sm:hidden p-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/></svg>
                    </button>
                    <div>
                        <h2 class="text-xl font-bold text-gray-900">@yield('page-title', 'Dashboard')</h2>
                        <p class="text-sm text-gray-500">@yield('page-subtitle', 'Sistem E-Tiket Report RS Efarina Etaham')</p>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <div class="hidden md:flex items-center gap-2 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-100">
                        <svg class="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                        <span id="currentDate" class="text-sm text-emerald-800 font-medium"></span>
                    </div>
                    <div class="flex items-center gap-3 pl-4 border-l border-gray-200">
                        <div class="text-right hidden sm:block">
                            <p class="text-sm font-semibold text-gray-900 truncate max-w-[160px]">{{ Auth::user()->name }}</p>
                            <p class="text-xs text-gray-500">
                                @if(Auth::user()->isAdmin()) Admin
                                @elseif(Auth::user()->isTechnician()) Teknisi
                                @else Kepala Divisi
                                @endif
                            </p>
                        </div>
                        <div class="w-10 h-10 bg-gradient-to-br from-emerald-600 to-emerald-800 text-white rounded-full flex items-center justify-center font-bold shadow-md">{{ strtoupper(substr(Auth::user()->name, 0, 1)) }}</div>
                    </div>
                </div>
            </div>
        </header>

        <!-- Main Body -->
        <main class="p-6 flex-1">
            @yield('content')
        </main>

        <!-- Footer -->
        <footer class="text-center text-sm text-gray-500 pb-6">
            <p>&copy; {{ date('Y') }} Sistem E-Tiket Report - RS Efarina Etaham Karawang</p>
        </footer>
    </div>

    <!-- Toast Notification -->
    <div id="toast" class="fixed bottom-6 right-6 z-50 transform translate-y-20 opacity-0 transition-all duration-300 pointer-events-none">
        <div class="bg-emerald-950 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 border border-emerald-800 max-w-sm">
            <svg id="toastIconSuccess" class="w-5 h-5 text-emerald-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            <svg id="toastIconError" class="w-5 h-5 text-rose-400 shrink-0 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
            <span id="toastMessage">Notifikasi</span>
        </div>
    </div>

    <!-- Flash Messages & Validation Errors (Toast) -->
    <script>
        @if(session('success'))
            showToast(@js(session('success')));
        @endif
        @if(session('error'))
            showToast(@js(session('error')), true);
        @endif
        @if($errors->any())
            showToast(@js($errors->first()), true);
        @endif
    </script>

    @stack('scripts')
</body>
</html>
