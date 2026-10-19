<?php

namespace Database\Seeders;

use App\Models\Category;
use App\Models\Division;
use App\Models\Ticket;
use App\Models\TicketLog;
use App\Models\User;
use Illuminate\Database\Console\Seeds\WithoutModelEvents;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    use WithoutModelEvents;

    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        // 1. Seed Divisions
        $igd = Division::create(['name' => 'Instalasi Gawat Darurat (IGD)', 'code' => 'DIV-IGD']);
        $icu = Division::create(['name' => 'Intensive Care Unit (ICU)', 'code' => 'DIV-ICU']);
        $farmasi = Division::create(['name' => 'Instalasi Farmasi', 'code' => 'DIV-FAR']);
        $ranap = Division::create(['name' => 'Rawat Inap', 'code' => 'DIV-RNP']);
        $keuangan = Division::create(['name' => 'Keuangan & SDM', 'code' => 'DIV-KEU']);

        // 2. Seed Categories
        $hardware = Category::create(['name' => 'Hardware (PC, Printer, Scanner)', 'sla_response_minutes' => 30, 'sla_resolve_minutes' => 120]);
        $software = Category::create(['name' => 'Software & OS', 'sla_response_minutes' => 60, 'sla_resolve_minutes' => 240]);
        $jaringan = Category::create(['name' => 'Jaringan & Internet', 'sla_response_minutes' => 15, 'sla_resolve_minutes' => 60]);
        $simrs = Category::create(['name' => 'SIMRS (Sistem Informasi RS)', 'sla_response_minutes' => 20, 'sla_resolve_minutes' => 120]);

        // 3. Seed Users
        // Admin / Kepala Unit IT
        $admin = User::create([
            'name' => 'Dr. Andi (Kepala IT)',
            'email' => 'admin@rs.com',
            'password' => bcrypt('admin-efarina-2026'),
            'role' => User::ROLE_ADMIN,
            'phone' => '081234567890',
            'is_active' => true,
        ]);

        // Technicians
        $teknisiHardware = User::create([
            'name' => 'Budi (Teknisi Hardware)',
            'email' => 'budi@rs.com',
            'password' => bcrypt('budi-hardware-2026'),
            'role' => User::ROLE_TECHNICIAN,
            'phone' => '081234567891',
            'is_active' => true,
        ]);

        $teknisiNetwork = User::create([
            'name' => 'Siti (Teknisi Network & SIMRS)',
            'email' => 'siti@rs.com',
            'password' => bcrypt('siti-network-2026'),
            'role' => User::ROLE_TECHNICIAN,
            'phone' => '081234567892',
            'is_active' => true,
        ]);

        // Division Heads
        $kaIgd = User::create([
            'name' => 'Ani (Ka. Unit IGD)',
            'email' => 'ani@rs.com',
            'password' => bcrypt('ani-igd-2026'),
            'role' => User::ROLE_DIVISION_HEAD,
            'division_id' => $igd->id,
            'phone' => '081234567893',
            'is_active' => true,
        ]);

        $kaFarmasi = User::create([
            'name' => 'Iwan (Ka. Unit Farmasi)',
            'email' => 'iwan@rs.com',
            'password' => bcrypt('iwan-farmasi-2026'),
            'role' => User::ROLE_DIVISION_HEAD,
            'division_id' => $farmasi->id,
            'phone' => '081234567894',
            'is_active' => true,
        ]);

        $kaIcu = User::create([
            'name' => 'Dewi (Ka. Unit ICU)',
            'email' => 'dewi@rs.com',
            'password' => bcrypt('dewi-icu-2026'),
            'role' => User::ROLE_DIVISION_HEAD,
            'division_id' => $icu->id,
            'phone' => '081234567895',
            'is_active' => true,
        ]);

        // 4. Seed Mock Tickets
        // Ticket 1: Open, reported by Ani (IGD) - Jaringan
        $t1 = Ticket::create([
            'ticket_number' => 'TKT-'.date('Ymd').'-0001',
            'creator_id' => $kaIgd->id,
            'division_id' => $igd->id,
            'category_id' => $jaringan->id,
            'subject' => 'Koneksi LAN ke SIMRS terputus',
            'description' => 'Komputer pendaftaran IGD tidak bisa terhubung ke server SIMRS, muncul error network timeout. Tolong segera ditangani karena antrean menumpuk.',
            'location' => 'Meja Pendaftaran IGD',
            'asset_code' => 'PC-IGD-004',
            'priority' => Ticket::PRIORITY_EMERGENCY,
            'status' => Ticket::STATUS_OPEN,
        ]);
        TicketLog::create([
            'ticket_id' => $t1->id,
            'user_id' => $kaIgd->id,
            'action' => 'Pelaporan Tiket',
            'note' => 'Tiket berhasil dibuat oleh Kepala Unit IGD dengan prioritas Emergency.',
        ]);

        // Ticket 2: Assigned / In Progress, reported by Iwan (Farmasi) - Hardware
        $t2 = Ticket::create([
            'ticket_number' => 'TKT-'.date('Ymd').'-0002',
            'creator_id' => $kaFarmasi->id,
            'technician_id' => $teknisiHardware->id,
            'division_id' => $farmasi->id,
            'category_id' => $hardware->id,
            'subject' => 'Printer Label Resep macet (Paper Jam)',
            'description' => 'Printer kasir farmasi macet terus menerus saat mencetak etiket obat. Sudah dibersihkan tapi tetap macet.',
            'location' => 'Depo Farmasi Rawat Jalan',
            'asset_code' => 'PRT-FAR-012',
            'priority' => Ticket::PRIORITY_HIGH,
            'status' => Ticket::STATUS_IN_PROGRESS,
            'assigned_at' => now()->subMinutes(30),
            'started_at' => now()->subMinutes(15),
        ]);
        TicketLog::create([
            'ticket_id' => $t2->id,
            'user_id' => $kaFarmasi->id,
            'action' => 'Pelaporan Tiket',
            'note' => 'Tiket dilaporkan.',
        ]);
        TicketLog::create([
            'ticket_id' => $t2->id,
            'user_id' => $admin->id,
            'action' => 'Penugasan Teknisi',
            'note' => 'Admin menugaskan tiket kepada Budi (Teknisi Hardware).',
        ]);
        TicketLog::create([
            'ticket_id' => $t2->id,
            'user_id' => $teknisiHardware->id,
            'action' => 'Mulai Penanganan',
            'note' => 'Teknisi mulai melakukan pengecekan unit printer.',
        ]);

        // Ticket 3: Pending, reported by Dewi (ICU) - Hardware
        $t3 = Ticket::create([
            'ticket_number' => 'TKT-'.date('Ymd').'-0003',
            'creator_id' => $kaIcu->id,
            'technician_id' => $teknisiHardware->id,
            'division_id' => $icu->id,
            'category_id' => $hardware->id,
            'subject' => 'PC Monitor Tanda Vital sering restart sendiri',
            'description' => 'Komputer monitor vital sign di bed 2 ICU mati mendadak lalu restart setiap 30 menit sekali. Sangat krusial.',
            'location' => 'ICU Bed 2',
            'asset_code' => 'PC-ICU-002',
            'priority' => Ticket::PRIORITY_EMERGENCY,
            'status' => Ticket::STATUS_PENDING,
            'assigned_at' => now()->subHours(2),
            'started_at' => now()->subHours(1)->subMinutes(30),
        ]);
        TicketLog::create([
            'ticket_id' => $t3->id,
            'user_id' => $kaIcu->id,
            'action' => 'Pelaporan Tiket',
            'note' => 'Tiket dilaporkan.',
        ]);
        TicketLog::create([
            'ticket_id' => $t3->id,
            'user_id' => $admin->id,
            'action' => 'Penugasan Teknisi',
            'note' => 'Ditugaskan ke Budi (Teknisi Hardware).',
        ]);
        TicketLog::create([
            'ticket_id' => $t3->id,
            'user_id' => $teknisiHardware->id,
            'action' => 'Mulai Penanganan',
            'note' => 'Teknisi menginvestigasi power supply unit (PSU).',
        ]);
        TicketLog::create([
            'ticket_id' => $t3->id,
            'user_id' => $teknisiHardware->id,
            'action' => 'Penundaan Pekerjaan',
            'note' => 'Pekerjaan ditunda: Power Supply Unit rusak total. Sedang menunggu PSU baru dari pengadaan logistik rumah sakit.',
        ]);

        // Ticket 4: Resolved, reported by Ani (IGD) - SIMRS
        $t4 = Ticket::create([
            'ticket_number' => 'TKT-'.date('Ymd', strtotime('-1 day')).'-0004',
            'creator_id' => $kaIgd->id,
            'technician_id' => $teknisiNetwork->id,
            'division_id' => $igd->id,
            'category_id' => $simrs->id,
            'subject' => 'SIMRS tidak bisa cetak gelang pasien baru',
            'description' => 'Saat input pasien baru dan klik cetak gelang, modul print crash dan tidak mengeluarkan kertas gelang.',
            'location' => 'Pendaftaran IGD',
            'asset_code' => 'PRT-IGD-009',
            'priority' => Ticket::PRIORITY_HIGH,
            'status' => Ticket::STATUS_RESOLVED,
            'assigned_at' => now()->subDays(1)->subHours(3),
            'started_at' => now()->subDays(1)->subHours(2),
            'resolved_at' => now()->subDays(1)->subHours(1),
        ]);
        TicketLog::create([
            'ticket_id' => $t4->id,
            'user_id' => $kaIgd->id,
            'action' => 'Pelaporan Tiket',
            'note' => 'Tiket dilaporkan.',
        ]);
        TicketLog::create([
            'ticket_id' => $t4->id,
            'user_id' => $admin->id,
            'action' => 'Penugasan Teknisi',
            'note' => 'Ditugaskan ke Siti (Teknisi Network & SIMRS).',
        ]);
        TicketLog::create([
            'ticket_id' => $t4->id,
            'user_id' => $teknisiNetwork->id,
            'action' => 'Mulai Penanganan',
            'note' => 'Pengecekan driver printer gelang dan servis cetak di SIMRS.',
        ]);
        TicketLog::create([
            'ticket_id' => $t4->id,
            'user_id' => $teknisiNetwork->id,
            'action' => 'Penyelesaian Masalah',
            'note' => 'Solusi: Driver printer di-reinstall dan servis cetak SIMRS direstart. Cetak gelang sudah berfungsi normal kembali.',
        ]);

        // Ticket 5: Closed, reported by Iwan (Farmasi) - Software
        $t5 = Ticket::create([
            'ticket_number' => 'TKT-'.date('Ymd', strtotime('-2 days')).'-0005',
            'creator_id' => $kaFarmasi->id,
            'technician_id' => $teknisiNetwork->id,
            'division_id' => $farmasi->id,
            'category_id' => $software->id,
            'subject' => 'Error login akun kasir farmasi',
            'description' => 'Akun atas nama user Rina selalu mendapat warning password salah meskipun sudah benar.',
            'location' => 'Kasir Depo Farmasi Utama',
            'priority' => Ticket::PRIORITY_MEDIUM,
            'status' => Ticket::STATUS_CLOSED,
            'assigned_at' => now()->subDays(2)->subHours(4),
            'started_at' => now()->subDays(2)->subHours(3),
            'resolved_at' => now()->subDays(2)->subHours(2),
            'closed_at' => now()->subDays(2)->subHours(1),
        ]);
        TicketLog::create([
            'ticket_id' => $t5->id,
            'user_id' => $kaFarmasi->id,
            'action' => 'Pelaporan Tiket',
            'note' => 'Tiket dilaporkan.',
        ]);
        TicketLog::create([
            'ticket_id' => $t5->id,
            'user_id' => $admin->id,
            'action' => 'Penugasan',
            'note' => 'Ditugaskan ke Siti.',
        ]);
        TicketLog::create([
            'ticket_id' => $t5->id,
            'user_id' => $teknisiNetwork->id,
            'action' => 'Pengecekan',
            'note' => 'Melakukan reset password user Rina.',
        ]);
        TicketLog::create([
            'ticket_id' => $t5->id,
            'user_id' => $teknisiNetwork->id,
            'action' => 'Penyelesaian',
            'note' => 'Solusi: Password di-reset menjadi default password123 dan user diminta langsung menggantinya setelah login berhasil.',
        ]);
        TicketLog::create([
            'ticket_id' => $t5->id,
            'user_id' => $kaFarmasi->id,
            'action' => 'Penutupan Tiket',
            'note' => 'Tiket dikonfirmasi selesai dan ditutup oleh Kepala Unit Farmasi.',
        ]);
    }
}
