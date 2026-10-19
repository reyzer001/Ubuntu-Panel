<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dashboard E-Tiket Report - RS Efarina Etaham</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Inter', sans-serif; }
    .sidebar-scroll::-webkit-scrollbar { width: 5px; }
    .sidebar-scroll::-webkit-scrollbar-track { background: transparent; }
    .sidebar-scroll::-webkit-scrollbar-thumb { background: #166534; border-radius: 4px; }
    .fade-in { animation: fadeIn 0.5s ease-in; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  </style>
</head>
<body class="bg-gray-50 text-gray-800">

  <!-- Mobile Overlay -->
  <div id="mobileOverlay" class="fixed inset-0 bg-black/50 z-30 hidden sm:hidden" onclick="toggleSidebar()"></div>

  <!-- Sidebar -->
  <aside id="sidebar" class="fixed top-0 left-0 z-40 w-64 h-screen transition-transform -translate-x-full sm:translate-x-0 bg-emerald-950 text-white sidebar-scroll overflow-y-auto">
    <div class="h-full px-4 py-6">
      <div class="flex items-center gap-3 mb-8 px-2">
        <div class="w-10 h-10 bg-emerald-600 rounded-lg flex items-center justify-center font-bold text-xl shadow-lg shadow-emerald-600/30">E</div>
        <div>
          <h1 class="text-lg font-bold leading-tight">E-Tiket Report</h1>
          <p class="text-xs text-emerald-300">RS Efarina Etaham</p>
        </div>
      </div>

      <nav class="space-y-1">
        <a href="#" class="flex items-center gap-3 px-3 py-2.5 bg-emerald-700 rounded-lg text-white font-medium shadow-md shadow-emerald-950/20">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
          Dashboard
        </a>
        <a href="#" onclick="showToast('Halaman Kelola Tiket')" class="flex items-center gap-3 px-3 py-2.5 text-emerald-200 hover:bg-emerald-900 hover:text-white rounded-lg transition-all duration-200">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
          Kelola Tiket
        </a>
        <a href="#" onclick="showToast('Halaman Pengguna')" class="flex items-center gap-3 px-3 py-2.5 text-emerald-200 hover:bg-emerald-900 hover:text-white rounded-lg transition-all duration-200">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"/></svg>
          Pengguna
        </a>
        <a href="#" onclick="showToast('Halaman Laporan')" class="flex items-center gap-3 px-3 py-2.5 text-emerald-200 hover:bg-emerald-900 hover:text-white rounded-lg transition-all duration-200">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
          Laporan
        </a>
        <a href="#" onclick="showToast('Halaman Pengaturan')" class="flex items-center gap-3 px-3 py-2.5 text-emerald-200 hover:bg-emerald-900 hover:text-white rounded-lg transition-all duration-200">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
          Pengaturan
        </a>
      </nav>

      <div class="mt-8 pt-6 border-t border-emerald-900">
        <p class="text-xs text-emerald-400 uppercase font-semibold mb-3 px-3 tracking-wider">Status Sistem</p>
        <div class="px-3 space-y-3">
          <div class="flex items-center justify-between text-sm">
            <span class="text-emerald-300">MySQL Database</span>
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
          <div class="flex items-center justify-between text-sm">
            <span class="text-emerald-300">API Response</span>
            <span class="text-emerald-400 font-medium">24ms</span>
          </div>
        </div>
      </div>

      <div class="mt-8 px-3">
        <div class="bg-emerald-900/50 rounded-lg p-4 border border-emerald-800">
          <p class="text-xs text-emerald-300 mb-1">Versi Sistem</p>
          <p class="text-sm font-semibold text-white">v1.0.0 (Waterfall)</p>
          <p class="text-xs text-emerald-400 mt-2">Laravel + MySQL</p>
        </div>
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
            <h2 class="text-xl font-bold text-gray-900">Dashboard Monitoring</h2>
            <p class="text-sm text-gray-500">Overview tiket dan pelaporan real-time</p>
          </div>
        </div>
        <div class="flex items-center gap-4">
          <div class="hidden md:flex items-center gap-2 bg-emerald-50 px-3 py-1.5 rounded-lg border border-emerald-100">
            <svg class="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
            <span id="currentDate" class="text-sm text-emerald-800 font-medium"></span>
          </div>
          <button class="relative p-2 text-gray-600 hover:bg-emerald-50 rounded-lg transition-colors" onclick="showNotification()">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
            <span class="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-red-500 rounded-full border-2 border-white animate-pulse"></span>
          </button>
          <div class="flex items-center gap-3 pl-4 border-l border-gray-200">
            <div class="text-right hidden sm:block">
              <p class="text-sm font-semibold text-gray-900">Administrator</p>
              <p class="text-xs text-gray-500">Admin</p>
            </div>
            <div class="w-10 h-10 bg-gradient-to-br from-emerald-600 to-emerald-800 text-white rounded-full flex items-center justify-center font-bold shadow-md">A</div>
          </div>
        </div>
      </div>
    </header>

    <!-- Dashboard Content -->
    <main class="p-6 flex-1">
      <!-- Stats Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in">
          <div class="flex items-center justify-between mb-4">
            <div class="p-2.5 bg-emerald-50 rounded-lg">
              <svg class="w-6 h-6 text-emerald-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"/></svg>
            </div>
            <span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full">Total</span>
          </div>
          <h3 class="text-2xl font-bold text-gray-900" id="totalTickets">1,247</h3>
          <p class="text-sm text-gray-500 mt-1">Total Tiket</p>
          <div class="mt-3 flex items-center text-sm text-emerald-700 font-medium">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"/></svg>
            <span>+12.5% dari bulan lalu</span>
          </div>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.1s">
          <div class="flex items-center justify-between mb-4">
            <div class="p-2.5 bg-amber-50 rounded-lg">
              <svg class="w-6 h-6 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <span class="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-1 rounded-full">Open</span>
          </div>
          <h3 class="text-2xl font-bold text-gray-900" id="openTickets">42</h3>
          <p class="text-sm text-gray-500 mt-1">Tiket Open</p>
          <div class="mt-3 w-full bg-gray-200 rounded-full h-1.5">
            <div class="bg-amber-500 h-1.5 rounded-full transition-all duration-1000" style="width: 35%"></div>
          </div>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.2s">
          <div class="flex items-center justify-between mb-4">
            <div class="p-2.5 bg-emerald-50 rounded-lg">
              <svg class="w-6 h-6 text-emerald-800" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            </div>
            <span class="text-xs font-medium text-emerald-800 bg-emerald-50 px-2 py-1 rounded-full">Dikerjakan</span>
          </div>
          <h3 class="text-2xl font-bold text-gray-900" id="inProgressTickets">38</h3>
          <p class="text-sm text-gray-500 mt-1">In Progress</p>
          <div class="mt-3 w-full bg-gray-200 rounded-full h-1.5">
            <div class="bg-emerald-700 h-1.5 rounded-full transition-all duration-1000" style="width: 28%"></div>
          </div>
        </div>

        <div class="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-lg transition-all duration-300 hover:-translate-y-1 fade-in" style="animation-delay: 0.3s">
          <div class="flex items-center justify-between mb-4">
            <div class="p-2.5 bg-emerald-50 rounded-lg">
              <svg class="w-6 h-6 text-emerald-700" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            </div>
            <span class="text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-1 rounded-full">Selesai</span>
          </div>
          <h3 class="text-2xl font-bold text-gray-900" id="closedTickets">1,167</h3>
          <p class="text-sm text-gray-500 mt-1">Tiket Closed</p>
          <div class="mt-3 flex items-center text-sm text-emerald-700 font-medium">
            <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
            <span>Tingkat penyelesaian 93.6%</span>
          </div>
        </div>
      </div>

      <!-- Charts Row -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <!-- Line Chart -->
        <div class="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.4s">
          <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
            <div>
              <h3 class="text-lg font-bold text-gray-900">Trend Tiket Bulanan</h3>
              <p class="text-sm text-gray-500">Rekapitulasi tiket masuk vs selesai 6 bulan terakhir</p>
            </div>
            <select id="periodSelect" onchange="updateTrendChart()" class="text-sm border border-gray-300 rounded-lg px-3 py-2 bg-white text-gray-700 focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none cursor-pointer hover:border-gray-400 transition-colors">
              <option value="6">6 Bulan Terakhir</option>
              <option value="12">1 Tahun Terakhir</option>
              <option value="2026">Tahun 2026</option>
            </select>
          </div>
          <div class="h-72 w-full" id="trendChart"></div>
        </div>

        <!-- Pie Chart -->
        <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.5s">
          <div class="mb-6">
            <h3 class="text-lg font-bold text-gray-900">Distribusi Status</h3>
            <p class="text-sm text-gray-500">Persentase berdasarkan status tiket</p>
          </div>
          <div class="h-56 w-full flex items-center justify-center" id="statusChart"></div>
          <div class="mt-4 grid grid-cols-2 gap-3">
            <div class="flex items-center gap-2 text-sm">
              <span class="w-3 h-3 rounded-full bg-emerald-600"></span>
              <span class="text-gray-600">Open</span>
              <span class="ml-auto font-semibold text-gray-900">42</span>
            </div>
            <div class="flex items-center gap-2 text-sm">
              <span class="w-3 h-3 rounded-full bg-emerald-800"></span>
              <span class="text-gray-600">In Progress</span>
              <span class="ml-auto font-semibold text-gray-900">38</span>
            </div>
            <div class="flex items-center gap-2 text-sm">
              <span class="w-3 h-3 rounded-full bg-amber-500"></span>
              <span class="text-gray-600">Pending</span>
              <span class="ml-auto font-semibold text-gray-900">15</span>
            </div>
            <div class="flex items-center gap-2 text-sm">
              <span class="w-3 h-3 rounded-full bg-emerald-500"></span>
              <span class="text-gray-600">Closed</span>
              <span class="ml-auto font-semibold text-gray-900">1,167</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Second Row: Category & Staff Performance -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.6s">
          <h3 class="text-lg font-bold text-gray-900 mb-1">Tiket per Kategori</h3>
          <p class="text-sm text-gray-500 mb-6">Distribusi berdasarkan jenis permasalahan</p>
          <div class="h-64 w-full" id="categoryChart"></div>
        </div>
        <div class="bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.7s">
          <h3 class="text-lg font-bold text-gray-900 mb-1">Tiket per Petugas</h3>
          <p class="text-sm text-gray-500 mb-6">Performa penanganan tiket oleh tim</p>
          <div class="space-y-4" id="staffPerformance">
            <div class="group">
              <div class="flex justify-between text-sm mb-1.5">
                <span class="font-medium text-gray-700 group-hover:text-emerald-700 transition-colors">Budi Santoso - Teknisi Senior</span>
                <span class="font-semibold text-gray-900">312 tiket</span>
              </div>
              <div class="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                <div class="bg-gradient-to-r from-emerald-600 to-emerald-800 h-2.5 rounded-full transition-all duration-1000 ease-out" style="width: 0%" data-width="92%"></div>
              </div>
            </div>
            <div class="group">
              <div class="flex justify-between text-sm mb-1.5">
                <span class="font-medium text-gray-700 group-hover:text-emerald-700 transition-colors">Dewi Lestari - Staff IT</span>
                <span class="font-semibold text-gray-900">278 tiket</span>
              </div>
              <div class="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                <div class="bg-gradient-to-r from-emerald-600 to-emerald-800 h-2.5 rounded-full transition-all duration-1000 ease-out" style="width: 0%" data-width="82%"></div>
              </div>
            </div>
            <div class="group">
              <div class="flex justify-between text-sm mb-1.5">
                <span class="font-medium text-gray-700 group-hover:text-emerald-700 transition-colors">Ahmad Fauzi - Helpdesk</span>
                <span class="font-semibold text-gray-900">245 tiket</span>
              </div>
              <div class="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                <div class="bg-gradient-to-r from-emerald-600 to-emerald-800 h-2.5 rounded-full transition-all duration-1000 ease-out" style="width: 0%" data-width="72%"></div>
              </div>
            </div>
            <div class="group">
              <div class="flex justify-between text-sm mb-1.5">
                <span class="font-medium text-gray-700 group-hover:text-emerald-700 transition-colors">Rina Wulandari - Operator</span>
                <span class="font-semibold text-gray-900">198 tiket</span>
              </div>
              <div class="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                <div class="bg-gradient-to-r from-emerald-600 to-emerald-800 h-2.5 rounded-full transition-all duration-1000 ease-out" style="width: 0%" data-width="58%"></div>
              </div>
            </div>
            <div class="group">
              <div class="flex justify-between text-sm mb-1.5">
                <span class="font-medium text-gray-700 group-hover:text-emerald-700 transition-colors">Siti Aminah - Admin</span>
                <span class="font-semibold text-gray-900">156 tiket</span>
              </div>
              <div class="w-full bg-gray-100 rounded-full h-2.5 overflow-hidden">
                <div class="bg-gradient-to-r from-emerald-600 to-emerald-800 h-2.5 rounded-full transition-all duration-1000 ease-out" style="width: 0%" data-width="46%"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent Tickets Table -->
      <div class="bg-white rounded-xl border border-gray-200 overflow-hidden fade-in" style="animation-delay: 0.8s">
        <div class="px-6 py-5 border-b border-gray-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 class="text-lg font-bold text-gray-900">Tiket Terkini</h3>
            <p class="text-sm text-gray-500">Daftar tiket terbaru yang memerlukan perhatian</p>
          </div>
          <div class="flex items-center gap-3">
            <div class="relative">
              <input type="text" id="searchTicket" onkeyup="searchTickets()" placeholder="Cari tiket..." class="pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none w-full sm:w-64 transition-all hover:border-gray-400">
              <svg class="w-4 h-4 text-gray-400 absolute left-3 top-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
            </div>
            <button onclick="openCreateModal()" class="px-4 py-2 bg-emerald-700 text-white text-sm font-medium rounded-lg hover:bg-emerald-800 transition-all shadow-md shadow-emerald-700/20 flex items-center gap-2 whitespace-nowrap">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>
              Buat Tiket
            </button>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead class="bg-gray-50 text-gray-700 uppercase text-xs font-semibold">
              <tr>
                <th class="px-6 py-4 cursor-pointer hover:bg-gray-100 transition-colors" onclick="sortTable(0)">ID Tiket ↕</th>
                <th class="px-6 py-4">Judul / Keluhan</th>
                <th class="px-6 py-4">Kategori</th>
                <th class="px-6 py-4">Pengaju</th>
                <th class="px-6 py-4">Petugas</th>
                <th class="px-6 py-4">Status</th>
                <th class="px-6 py-4">Prioritas</th>
                <th class="px-6 py-4 cursor-pointer hover:bg-gray-100 transition-colors" onclick="sortTable(7)">Tanggal ↕</th>
                <th class="px-6 py-4 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100" id="ticketTableBody">
              <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-mono font-medium text-emerald-700">#TKT-2026-0842</td>
                <td class="px-6 py-4 font-medium text-gray-900">Gangguan jaringan WiFi ruang rawat inap lt.3</td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-100">Jaringan</span></td>
                <td class="px-6 py-4 text-gray-600">dr. Siti Rahayu</td>
                <td class="px-6 py-4 text-gray-600">Budi Santoso</td>
                <td class="px-6 py-4"><span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>Open</span></td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-100">High</span></td>
                <td class="px-6 py-4 text-gray-500">21 Agu 2026</td>
                <td class="px-6 py-4 text-right">
                  <button onclick="showDetail('#TKT-2026-0842', 'Gangguan jaringan WiFi ruang rawat inap lt.3', 'Jaringan', 'dr. Siti Rahayu', 'Budi Santoso', 'Open', 'High', '21 Agustus 2026')" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</button>
                </td>
              </tr>
              <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-mono font-medium text-emerald-700">#TKT-2026-0841</td>
                <td class="px-6 py-4 font-medium text-gray-900">Printer di loket pendaftaran tidak merespon</td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-50 text-purple-700 border border-purple-100">Hardware</span></td>
                <td class="px-6 py-4 text-gray-600">Kasir 1 - Rina</td>
                <td class="px-6 py-4 text-gray-600">Dewi Lestari</td>
                <td class="px-6 py-4"><span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-700 animate-pulse"></span>In Progress</span></td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-50 text-orange-700 border border-orange-100">Medium</span></td>
                <td class="px-6 py-4 text-gray-500">21 Agu 2026</td>
                <td class="px-6 py-4 text-right">
                  <button onclick="showDetail('#TKT-2026-0841', 'Printer di loket pendaftaran tidak merespon', 'Hardware', 'Kasir 1 - Rina', 'Dewi Lestari', 'In Progress', 'Medium', '21 Agustus 2026')" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</button>
                </td>
              </tr>
              <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-mono font-medium text-emerald-700">#TKT-2026-0840</td>
                <td class="px-6 py-4 font-medium text-gray-900">Aplikasi rekam medik error saat input pasien baru</td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-100">Software</span></td>
                <td class="px-6 py-4 text-gray-600">dr. Bambang</td>
                <td class="px-6 py-4 text-gray-600">Ahmad Fauzi</td>
                <td class="px-6 py-4"><span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-700 animate-pulse"></span>In Progress</span></td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-100">High</span></td>
                <td class="px-6 py-4 text-gray-500">20 Agu 2026</td>
                <td class="px-6 py-4 text-right">
                  <button onclick="showDetail('#TKT-2026-0840', 'Aplikasi rekam medik error saat input pasien baru', 'Software', 'dr. Bambang', 'Ahmad Fauzi', 'In Progress', 'High', '20 Agustus 2026')" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</button>
                </td>
              </tr>
              <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-mono font-medium text-emerald-700">#TKT-2026-0839</td>
                <td class="px-6 py-4 font-medium text-gray-900">Request instalasi monitor tambah di ruang ICU</td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700 border border-gray-200">Request</span></td>
                <td class="px-6 py-4 text-gray-600">Kepala Ruang ICU</td>
                <td class="px-6 py-4 text-gray-600">-</td>
                <td class="px-6 py-4"><span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>Open</span></td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-100">Low</span></td>
                <td class="px-6 py-4 text-gray-500">20 Agu 2026</td>
                <td class="px-6 py-4 text-right">
                  <button onclick="showDetail('#TKT-2026-0839', 'Request instalasi monitor tambah di ruang ICU', 'Request', 'Kepala Ruang ICU', '-', 'Open', 'Low', '20 Agustus 2026')" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</button>
                </td>
              </tr>
              <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-mono font-medium text-emerald-700">#TKT-2026-0838</td>
                <td class="px-6 py-4 font-medium text-gray-900">Ganti password akun SIP untuk 5 staff baru</td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-100">Akses</span></td>
                <td class="px-6 py-4 text-gray-600">HRD</td>
                <td class="px-6 py-4 text-gray-600">Siti Aminah</td>
                <td class="px-6 py-4"><span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-50 text-yellow-700 border border-yellow-200"><span class="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>Pending</span></td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-100">Low</span></td>
                <td class="px-6 py-4 text-gray-500">19 Agu 2026</td>
                <td class="px-6 py-4 text-right">
                  <button onclick="showDetail('#TKT-2026-0838', 'Ganti password akun SIP untuk 5 staff baru', 'Akses', 'HRD', 'Siti Aminah', 'Pending', 'Low', '19 Agustus 2026')" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</button>
                </td>
              </tr>
              <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4 font-mono font-medium text-emerald-700">#TKT-2026-0837</td>
                <td class="px-6 py-4 font-medium text-gray-900">Backup data server farmasi otomatis gagal</td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-100">Software</span></td>
                <td class="px-6 py-4 text-gray-600">IT Support</td>
                <td class="px-6 py-4 text-gray-600">Budi Santoso</td>
                <td class="px-6 py-4"><span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"><span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>Closed</span></td>
                <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-100">High</span></td>
                <td class="px-6 py-4 text-gray-500">19 Agu 2026</td>
                <td class="px-6 py-4 text-right">
                  <button onclick="showDetail('#TKT-2026-0837', 'Backup data server farmasi otomatis gagal', 'Software', 'IT Support', 'Budi Santoso', 'Closed', 'High', '19 Agustus 2026')" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="px-6 py-4 border-t border-gray-200 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p class="text-sm text-gray-500">Menampilkan <span id="showingCount">1-6</span> dari <span id="totalCount">1,247</span> tiket</p>
          <div class="flex items-center gap-2">
            <button onclick="showToast('Berada di halaman pertama')" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">Sebelumnya</button>
            <button class="px-3 py-1.5 bg-emerald-700 text-white rounded-lg text-sm font-medium shadow-sm">1</button>
            <button onclick="showToast('Memuat halaman 2')" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">2</button>
            <button onclick="showToast('Memuat halaman 3')" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">3</button>
            <button onclick="showToast('Memuat halaman berikutnya')" class="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-600 hover:bg-gray-50 transition-colors">Selanjutnya</button>
          </div>
        </div>
      </div>

      <!-- Activity Log -->
      <div class="mt-8 bg-white rounded-xl border border-gray-200 p-6 fade-in" style="animation-delay: 0.9s">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-bold text-gray-900">Aktivitas Terkini</h3>
          <button onclick="refreshActivity()" class="text-sm text-emerald-700 hover:text-emerald-900 font-medium flex items-center gap-1">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            Refresh
          </button>
        </div>
        <div class="space-y-4" id="activityLog">
          <div class="flex gap-4 items-start">
            <div class="w-8 h-8 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center flex-shrink-0 text-xs font-bold">BS</div>
            <div class="flex-1">
              <p class="text-sm text-gray-900"><span class="font-semibold">Budi Santoso</span> mengubah status tiket <span class="font-mono text-emerald-700 bg-emerald-50 px-1 rounded">#TKT-2026-0837</span> menjadi <span class="font-medium text-emerald-700">Closed</span></p>
              <p class="text-xs text-gray-500 mt-0.5">2 jam yang lalu</p>
            </div>
          </div>
          <div class="flex gap-4 items-start">
            <div class="w-8 h-8 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center flex-shrink-0 text-xs font-bold">DL</div>
            <div class="flex-1">
              <p class="text-sm text-gray-900"><span class="font-semibold">Dewi Lestari</span> mulai mengerjakan tiket <span class="font-mono text-emerald-700 bg-emerald-50 px-1 rounded">#TKT-2026-0841</span></p>
              <p class="text-xs text-gray-500 mt-0.5">3 jam yang lalu</p>
            </div>
          </div>
          <div class="flex gap-4 items-start">
            <div class="w-8 h-8 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center flex-shrink-0 text-xs font-bold">AF</div>
            <div class="flex-1">
              <p class="text-sm text-gray-900"><span class="font-semibold">Ahmad Fauzi</span> menambahkan komentar pada tiket <span class="font-mono text-emerald-700 bg-emerald-50 px-1 rounded">#TKT-2026-0840</span></p>
              <p class="text-xs text-gray-500 mt-0.5">5 jam yang lalu</p>
            </div>
          </div>
          <div class="flex gap-4 items-start">
            <div class="w-8 h-8 rounded-full bg-gray-100 text-gray-700 flex items-center justify-center flex-shrink-0 text-xs font-bold">SA</div>
            <div class="flex-1">
              <p class="text-sm text-gray-900"><span class="font-semibold">Siti Aminah</span> membuat tiket baru <span class="font-mono text-emerald-700 bg-emerald-50 px-1 rounded">#TKT-2026-0842</span></p>
              <p class="text-xs text-gray-500 mt-0.5">6 jam yang lalu</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <footer class="mt-8 text-center text-sm text-gray-500 pb-6">
        <p>© 2026 Sistem E-Tiket Report - RS Efarina Etaham Karawang</p>
        <p class="mt-1">Agustinus Fernando Manullang | Teknik Informatika - Universitas Efarina</p>
      </footer>
    </main>
  </div>

  <!-- Modal Detail Tiket -->
  <div id="detailModal" class="fixed inset-0 z-50 hidden">
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="closeModal()"></div>
    <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-2xl w-full max-w-lg p-6 transform transition-all scale-95 opacity-0" id="modalContent">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-bold text-gray-900" id="modalTitle">Detail Tiket</h3>
        <button onclick="closeModal()" class="text-gray-400 hover:text-gray-600">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="space-y-3 text-sm" id="modalBody">
        <!-- Content injected by JS -->
      </div>
      <div class="mt-6 flex justify-end gap-3">
        <button onclick="closeModal()" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">Tutup</button>
        <button onclick="saveTicketChanges()" class="px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-colors">Simpan Perubahan</button>
      </div>
    </div>
  </div>

  <!-- Modal Buat Tiket Baru -->
  <div id="createModal" class="fixed inset-0 z-50 hidden">
    <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" onclick="closeCreateModal()"></div>
    <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-xl shadow-2xl w-full max-w-lg p-6 transform transition-all scale-95 opacity-0" id="createModalContent">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-bold text-gray-900">Buat Tiket Baru</h3>
        <button onclick="closeCreateModal()" class="text-gray-400 hover:text-gray-600">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>
      <form onsubmit="handleCreateTicket(event)" class="space-y-4 text-sm">
        <div>
          <label class="block text-gray-700 font-medium mb-1">Judul / Keluhan</label>
          <input type="text" id="newTitle" required placeholder="Contoh: Gangguan PC Poli Anak" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none">
        </div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-gray-700 font-medium mb-1">Kategori</label>
            <select id="newCategory" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none">
              <option value="Jaringan">Jaringan</option>
              <option value="Hardware">Hardware</option>
              <option value="Software">Software</option>
              <option value="Request">Request</option>
              <option value="Akses">Akses</option>
            </select>
          </div>
          <div>
            <label class="block text-gray-700 font-medium mb-1">Prioritas</label>
            <select id="newPriority" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none">
              <option value="Low">Low</option>
              <option value="Medium">Medium</option>
              <option value="High">High</option>
            </select>
          </div>
        </div>
        <div>
          <label class="block text-gray-700 font-medium mb-1">Nama Pengaju</label>
          <input type="text" id="newRequester" required placeholder="Nama lengkap / Ruangan" class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none">
        </div>
        <div>
          <label class="block text-gray-700 font-medium mb-1">Deskripsi Kendala</label>
          <textarea id="newDesc" rows="3" required placeholder="Jelaskan kendala secara mendetail..." class="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-600 focus:border-emerald-600 outline-none"></textarea>
        </div>
        <div class="mt-6 flex justify-end gap-3">
          <button type="button" onclick="closeCreateModal()" class="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors">Batal</button>
          <button type="submit" class="px-4 py-2 bg-emerald-700 text-white rounded-lg hover:bg-emerald-800 transition-colors">Simpan Tiket</button>
        </div>
      </form>
    </div>
  </div>

  <!-- Toast Notification -->
  <div id="toast" class="fixed bottom-6 right-6 z-50 transform translate-y-20 opacity-0 transition-all duration-300">
    <div class="bg-emerald-950 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 border border-emerald-800">
      <svg class="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
      <span id="toastMessage">Notifikasi</span>
    </div>
  </div>

  <script>
    // Date Display
    const dateOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('currentDate').textContent = new Date().toLocaleDateString('id-ID', dateOptions);

    // Sidebar Toggle
    function toggleSidebar() {
      const sidebar = document.getElementById('sidebar');
      const overlay = document.getElementById('mobileOverlay');
      sidebar.classList.toggle('-translate-x-full');
      overlay.classList.toggle('hidden');
    }

    // Toast
    function showToast(message) {
      const toast = document.getElementById('toast');
      document.getElementById('toastMessage').textContent = message;
      toast.classList.remove('translate-y-20', 'opacity-0');
      setTimeout(() => {
        toast.classList.add('translate-y-20', 'opacity-0');
      }, 3000);
    }

    // Notification
    function showNotification() {
      showToast('Anda memiliki 3 notifikasi baru sistem!');
    }

    // Modal Detail
    function showDetail(ticketId, title, category, requester, officer, status, priority, date) {
      const modal = document.getElementById('detailModal');
      const content = document.getElementById('modalContent');
      const body = document.getElementById('modalBody');
      document.getElementById('modalTitle').textContent = 'Detail ' + ticketId;

      body.innerHTML = `
        <div class="grid grid-cols-2 gap-4">
          <div><p class="text-gray-500 text-xs uppercase font-semibold">Status</p><p class="font-medium text-emerald-700">${status}</p></div>
          <div><p class="text-gray-500 text-xs uppercase font-semibold">Prioritas</p><p class="font-medium text-red-600">${priority}</p></div>
          <div><p class="text-gray-500 text-xs uppercase font-semibold">Kategori</p><p class="font-medium">${category}</p></div>
          <div><p class="text-gray-500 text-xs uppercase font-semibold">Dibuat</p><p class="font-medium">${date}</p></div>
          <div><p class="text-gray-500 text-xs uppercase font-semibold">Pengaju</p><p class="font-medium">${requester}</p></div>
          <div><p class="text-gray-500 text-xs uppercase font-semibold">Petugas</p><p class="font-medium">${officer}</p></div>
        </div>
        <div class="mt-4 p-3 bg-gray-50 rounded-lg">
          <p class="text-gray-500 text-xs uppercase font-semibold mb-1">Judul / Keluhan</p>
          <p class="text-gray-700 font-medium">${title}</p>
        </div>
        <div class="mt-3">
          <p class="text-gray-500 text-xs uppercase font-semibold mb-1">Riwayat Penanganan</p>
          <div class="space-y-2 text-xs">
            <div class="flex gap-2"><span class="text-gray-400">08:30</span><span>Tiket berhasil direkam ke dalam database sistem</span></div>
            <div class="flex gap-2"><span class="text-gray-400">09:00</span><span>Petugas teknis meninjau laporan kerusakan</span></div>
          </div>
        </div>
      `;

      modal.classList.remove('hidden');
      setTimeout(() => {
        content.classList.remove('scale-95', 'opacity-0');
        content.classList.add('scale-100', 'opacity-100');
      }, 10);
    }

    function closeModal() {
      const modal = document.getElementById('detailModal');
      const content = document.getElementById('modalContent');
      content.classList.remove('scale-100', 'opacity-100');
      content.classList.add('scale-95', 'opacity-0');
      setTimeout(() => {
        modal.classList.add('hidden');
      }, 200);
    }

    function saveTicketChanges() {
      closeModal();
      showToast('Perubahan tiket berhasil disimpan!');
    }

    // Modal Create Ticket
    function openCreateModal() {
      const modal = document.getElementById('createModal');
      const content = document.getElementById('createModalContent');
      modal.classList.remove('hidden');
      setTimeout(() => {
        content.classList.remove('scale-95', 'opacity-0');
        content.classList.add('scale-100', 'opacity-100');
      }, 10);
    }

    function closeCreateModal() {
      const modal = document.getElementById('createModal');
      const content = document.getElementById('createModalContent');
      content.classList.remove('scale-100', 'opacity-100');
      content.classList.add('scale-95', 'opacity-0');
      setTimeout(() => {
        modal.classList.add('hidden');
      }, 200);
    }

    function handleCreateTicket(e) {
      e.preventDefault();
      const title = document.getElementById('newTitle').value;
      const category = document.getElementById('newCategory').value;
      const priority = document.getElementById('newPriority').value;
      const requester = document.getElementById('newRequester').value;

      const tbody = document.getElementById('ticketTableBody');
      const newRow = document.createElement('tr');
      newRow.className = 'hover:bg-gray-50 transition-colors';
      const randomId = '#TKT-2026-0' + Math.floor(100 + Math.random() * 900);
      const todayStr = '21 Agu 2026';

      newRow.innerHTML = `
        <td class="px-6 py-4 font-mono font-medium text-emerald-700">${randomId}</td>
        <td class="px-6 py-4 font-medium text-gray-900">${title}</td>
        <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-800 border border-emerald-100">${category}</span></td>
        <td class="px-6 py-4 text-gray-600">${requester}</td>
        <td class="px-6 py-4 text-gray-600">Belum ditugaskan</td>
        <td class="px-6 py-4"><span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200"><span class="w-1.5 h-1.5 rounded-full bg-amber-500"></span>Open</span></td>
        <td class="px-6 py-4"><span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-100">${priority}</span></td>
        <td class="px-6 py-4 text-gray-500">${todayStr}</td>
        <td class="px-6 py-4 text-right">
          <button onclick="showDetail('${randomId}', '${title}', '${category}', '${requester}', 'Belum ditugaskan', 'Open', '${priority}', '21 Agustus 2026')" class="text-emerald-700 hover:text-emerald-900 font-medium text-xs hover:underline">Detail</button>
        </td>
      `;
      tbody.prepend(newRow);

      // Update total counter
      const totalEl = document.getElementById('totalTickets');
      const countEl = document.getElementById('totalCount');
      const currentVal = parseInt(totalEl.textContent.replace(/,/g, '')) + 1;
      totalEl.textContent = currentVal.toLocaleString('id-ID');
      countEl.textContent = currentVal.toLocaleString('id-ID');

      closeCreateModal();
      showToast('Tiket baru berhasil dibuat!');
    }

    // Search
    function searchTickets() {
      const input = document.getElementById('searchTicket').value.toLowerCase();
      const rows = document.querySelectorAll('#ticketTableBody tr');
      let visible = 0;
      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(input)) {
          row.style.display = '';
          visible++;
        } else {
          row.style.display = 'none';
        }
      });
      document.getElementById('showingCount').textContent = visible > 0 ? `1-${visible}` : '0';
    }

    // Sort
    let sortDir = 1;
    function sortTable(colIndex) {
      const tbody = document.getElementById('ticketTableBody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {
        const aText = a.cells[colIndex].textContent.trim();
        const bText = b.cells[colIndex].textContent.trim();
        return sortDir * aText.localeCompare(bText);
      });
      sortDir *= -1;
      rows.forEach(row => tbody.appendChild(row));
    }

    // Refresh Activity
    function refreshActivity() {
      showToast('Aktivitas berhasil diperbarui!');
    }

    // Trend Chart (Line)
    let trendChart = echarts.init(document.getElementById('trendChart'));
    const trendData = {
      '6': {
        labels: ['Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu'],
        masuk: [180, 195, 210, 188, 245, 229],
        selesai: [165, 188, 205, 195, 238, 220]
      },
      '12': {
        labels: ['Sep', 'Okt', 'Nov', 'Des', 'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu'],
        masuk: [150, 165, 170, 160, 175, 180, 180, 195, 210, 188, 245, 229],
        selesai: [140, 155, 168, 158, 170, 175, 165, 188, 205, 195, 238, 220]
      },
      '2026': {
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu'],
        masuk: [175, 180, 180, 195, 210, 188, 245, 229],
        selesai: [170, 175, 165, 188, 205, 195, 238, 220]
      }
    };

    function updateTrendChart() {
      const period = document.getElementById('periodSelect').value;
      const data = trendData[period];
      trendChart.setOption({
        xAxis: { data: data.labels },
        series: [
          { data: data.masuk },
          { data: data.selesai }
        ]
      });
    }

    trendChart.setOption({
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(255,255,255,0.95)', borderColor: '#e5e7eb', textStyle: { color: '#374151' }, axisPointer: { lineStyle: { color: '#e5e7eb' } } },
      legend: { data: ['Tiket Masuk', 'Tiket Selesai'], bottom: 0, textStyle: { color: '#6b7280' } },
      grid: { left: '3%', right: '4%', bottom: '15%', top: '5%', containLabel: true },
      xAxis: { type: 'category', boundaryGap: false, data: trendData['6'].labels, axisLine: { lineStyle: { color: '#e5e7eb' } }, axisLabel: { color: '#6b7280' } },
      yAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: '#f3f4f6' } }, axisLabel: { color: '#6b7280' } },
      series: [
        { name: 'Tiket Masuk', type: 'line', smooth: true, data: trendData['6'].masuk, itemStyle: { color: '#047857' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(4,120,87,0.2)' }, { offset: 1, color: 'rgba(4,120,87,0.02)' }] } }, lineStyle: { width: 3 } },
        { name: 'Tiket Selesai', type: 'line', smooth: true, data: trendData['6'].selesai, itemStyle: { color: '#10b981' }, areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(16,185,129,0.2)' }, { offset: 1, color: 'rgba(16,185,129,0.02)' }] } }, lineStyle: { width: 3 } }
      ]
    });

    // Status Chart (Pie)
    let statusChart = echarts.init(document.getElementById('statusChart'));
    statusChart.setOption({
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)', backgroundColor: 'rgba(255,255,255,0.95)', borderColor: '#e5e7eb', textStyle: { color: '#374151' } },
      series: [{
        type: 'pie',
        radius: ['45%', '70%'],
        avoidLabelOverlap: false,
        itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
        data: [
          { value: 42, name: 'Open', itemStyle: { color: '#047857' } },
          { value: 38, name: 'In Progress', itemStyle: { color: '#065f46' } },
          { value: 15, name: 'Pending', itemStyle: { color: '#f59e0b' } },
          { value: 1167, name: 'Closed', itemStyle: { color: '#10b981' } }
        ]
      }]
    });

    // Category Chart (Bar)
    let categoryChart = echarts.init(document.getElementById('categoryChart'));
    categoryChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(255,255,255,0.95)', borderColor: '#e5e7eb', textStyle: { color: '#374151' } },
      grid: { left: '3%', right: '4%', bottom: '3%', top: '3%', containLabel: true },
      xAxis: { type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: '#f3f4f6' } }, axisLabel: { color: '#6b7280' } },
      yAxis: { type: 'category', data: ['Lainnya', 'Akses', 'Request', 'Software', 'Hardware', 'Jaringan'], axisLine: { lineStyle: { color: '#e5e7eb' } }, axisLabel: { color: '#6b7280' } },
      series: [{
        type: 'bar',
        data: [45, 78, 112, 198, 234, 312],
        itemStyle: { color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: '#34d399' }, { offset: 1, color: '#047857' }] }, borderRadius: [0, 4, 4, 0] },
        barWidth: '60%',
        label: { show: true, position: 'right', color: '#6b7280', fontSize: 11 }
      }]
    });

    // Responsive resize
    window.addEventListener('resize', () => {
      trendChart.resize();
      statusChart.resize();
      categoryChart.resize();
    });

    // Animate progress bars
    setTimeout(() => {
      document.querySelectorAll('[data-width]').forEach(bar => {
        bar.style.width = bar.getAttribute('data-width');
      });
    }, 500);

    // Simulate real-time updates
    setInterval(() => {
      const totalEl = document.getElementById('totalTickets');
      const current = parseInt(totalEl.textContent.replace(/,/g, ''));
      if (Math.random() > 0.7) {
        totalEl.textContent = (current + 1).toLocaleString('id-ID');
        document.getElementById('totalCount').textContent = (current + 1).toLocaleString('id-ID');
      }
    }, 15000);

    // Keyboard shortcut
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeModal();
        closeCreateModal();
      }
      if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        document.getElementById('searchTicket').focus();
      }
    });
  </script>
</body>
</html>