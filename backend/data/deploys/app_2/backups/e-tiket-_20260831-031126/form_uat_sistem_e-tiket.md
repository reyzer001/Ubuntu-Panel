# FORM USER ACCEPTANCE TEST (UAT)
## Sistem E-Tiket IT Support
### RS Efarina Etaham Karawang

---

## A. Identitas Pengujian

| Item | Keterangan |
|---|---|
| Nama sistem | Sistem E-Tiket IT Support |
| Versi aplikasi | ______________________________ |
| Lingkungan pengujian | [ ] Lokal  [ ] Staging  [ ] Produksi  [ ] Cloudflare Tunnel |
| URL pengujian | ______________________________ |
| Tanggal pengujian | ____ / ____ / ______ |
| Nama penguji | ______________________________ |
| Jabatan/unit penguji | ______________________________ |
| Pendamping/pengembang | ______________________________ |

## B. Petunjuk Pengisian

1. Jalankan setiap skenario menggunakan akun dan data uji yang tersedia.
2. Isi kolom hasil aktual berdasarkan perilaku aplikasi saat diuji.
3. Beri nilai sesuai skala berikut:

| Nilai | Keterangan |
|---:|---|
| 1 | Tidak berfungsi / sangat tidak sesuai |
| 2 | Berfungsi sebagian besar tidak sesuai |
| 3 | Berfungsi cukup / perlu perbaikan |
| 4 | Berfungsi baik dengan catatan kecil |
| 5 | Berfungsi sangat baik dan sesuai kebutuhan |

4. Isi status dengan **Diterima** jika fungsi memenuhi kebutuhan, atau **Tidak Diterima** jika masih terdapat kendala.

## C. Daftar Pengujian Fitur

| No. | Modul/Fitur | Skenario Pengujian | Hasil yang Diharapkan | Hasil Aktual | Nilai (1-5) | Status | Catatan/Koreksi |
|---:|---|---|---|---|---:|---|---|
| 1 | Autentikasi | Login menggunakan email dan kata sandi yang valid | Pengguna berhasil masuk ke dashboard sesuai perannya |  |  |  |  |
| 2 | Autentikasi | Login dengan email atau kata sandi yang salah | Sistem menolak login dan menampilkan pesan kesalahan |  |  |  |  |
| 3 | Autentikasi | Logout dari aplikasi | Sesi pengguna berakhir dan diarahkan ke halaman login |  |  |  |  |
| 4 | Hak Akses | Pengguna membuka menu sesuai peran | Pengguna hanya dapat melihat dan menjalankan fitur sesuai hak akses |  |  |  |  |
| 5 | Dashboard | Membuka dashboard setelah login | Ringkasan jumlah dan status tiket tampil dari database |  |  |  |  |
| 6 | Dashboard | Melihat dashboard sebagai admin, teknisi, dan kepala divisi | Data dashboard sesuai ruang lingkup peran pengguna |  |  |  |  |
| 7 | Tiket | Membuat tiket baru dengan data lengkap | Tiket tersimpan dan memperoleh nomor tiket |  |  |  |  |
| 8 | Tiket | Membuat tiket dengan data wajib yang kosong | Sistem menolak penyimpanan dan menampilkan validasi |  |  |  |  |
| 9 | Tiket | Melihat daftar tiket | Daftar tiket tampil dengan informasi nomor, subjek, status, prioritas, dan tanggal |  |  |  |  |
| 10 | Tiket | Membuka detail tiket | Detail tiket, pelapor, unit, kategori, dan riwayat tampil dengan benar |  |  |  |  |
| 11 | Penugasan | Admin menugaskan tiket kepada teknisi | Teknisi tersimpan pada tiket dan status/riwayat diperbarui |  |  |  |  |
| 12 | Status Tiket | Teknisi memulai penanganan tiket | Status berubah sesuai alur dan waktu mulai tercatat |  |  |  |  |
| 13 | Status Tiket | Menunda, menyelesaikan, menutup, dan membuka kembali tiket | Perubahan status mengikuti hak akses dan tercatat di log |  |  |  |  |
| 15 | Manajemen Pengguna | Admin menambah pengguna baru | Data pengguna tersimpan dan dapat digunakan untuk login |  |  |  |  |
| 16 | Manajemen Pengguna | Admin mengubah data atau menonaktifkan pengguna | Perubahan tersimpan dan pengguna nonaktif tidak dapat login |  |  |  |  |
| 17 | Kategori dan SLA | Admin menambah atau mengubah kategori | Kategori dan waktu SLA tersimpan serta tersedia saat membuat tiket |  |  |  |  |
| 18 | Laporan | Membuka halaman laporan dengan filter periode | Data laporan sesuai periode dan hak akses pengguna |  |  |  |  |
| 19 | Laporan Excel | Mengunduh laporan Excel | File `.xlsx` berhasil diunduh, dapat dibuka, dan berisi data database |  |  |  |  |
| 20 | Laporan Excel | Mengunduh laporan tanpa data pada periode tertentu | File tetap valid dan menampilkan rekap bernilai nol tanpa error |  |  |  |  |
| 21 | Pengaturan | Admin mengunggah atau mengganti logo perusahaan | Logo tersimpan, tampil pada aplikasi, dan tersedia pada laporan |  |  |  |  |
| 22 | Akses Cloudflare | Membuka URL Cloudflare pada halaman login, dashboard, tiket, dan laporan | Seluruh halaman dapat diakses dan URL tidak kembali ke `localhost` |  |  |  |  |
| 23 | Database | Membuat dan mengubah data melalui aplikasi | Data tetap tersedia setelah logout, login ulang, dan refresh halaman |  |  |  |  |
| 24 | Keamanan | Pengguna tanpa hak mencoba membuka URL admin | Sistem menolak akses dan tidak menampilkan data admin |  |  |  |  |

## D. Rekapitulasi Penilaian

| Keterangan | Hasil |
|---|---:|
| Jumlah fitur diuji | 24 |
| Jumlah fitur Diterima | ______ |
| Jumlah fitur Tidak Diterima | ______ |
| Total nilai diperoleh | ______ |
| Nilai maksimum | 120 |
| Persentase nilai | ______ % |

**Rumus persentase:**

`(Total nilai diperoleh / 120) x 100%`

### Kriteria Keputusan

| Persentase | Keputusan |
|---:|---|
| 90% - 100% | Diterima tanpa perbaikan mayor |
| 75% - 89% | Diterima dengan catatan/perbaikan minor |
| Di bawah 75% | Tidak diterima dan perlu pengujian ulang |

**Keputusan akhir UAT:**

[ ] DITERIMA

[ ] DITERIMA DENGAN CATATAN

[ ] TIDAK DITERIMA

Catatan keputusan:

______________________________________________________________________________

______________________________________________________________________________

______________________________________________________________________________

## E. Daftar Perbaikan dan Pengujian Ulang

| No. | Temuan/Kendala | Prioritas | Rencana Perbaikan | Penanggung Jawab | Target Selesai | Status Uji Ulang |
|---:|---|---|---|---|---|---|
| 1 |  | [ ] Tinggi [ ] Sedang [ ] Rendah |  |  |  |  |
| 2 |  | [ ] Tinggi [ ] Sedang [ ] Rendah |  |  |  |  |
| 3 |  | [ ] Tinggi [ ] Sedang [ ] Rendah |  |  |  |  |
| 4 |  | [ ] Tinggi [ ] Sedang [ ] Rendah |  |  |  |  |
| 5 |  | [ ] Tinggi [ ] Sedang [ ] Rendah |  |  |  |  |

## F. Persetujuan dan Tanda Tangan

Dengan ditandatanganinya formulir ini, pihak penguji menyatakan bahwa pengujian UAT telah dilakukan berdasarkan skenario di atas dan keputusan akhir telah disepakati.

| Penguji/Penerima Sistem | Penanggung Jawab IT | Perwakilan Manajemen |
|---|---|---|
|  |  |  |
|  |  |  |
| **Nama:** ____________________ | **Nama:** ____________________ | **Nama:** ____________________ |
| **Jabatan:** __________________ | **Jabatan:** __________________ | **Jabatan:** __________________ |
| **Tanggal:** ____ / ____ / ____ | **Tanggal:** ____ / ____ / ____ | **Tanggal:** ____ / ____ / ____ |
| **Tanda tangan:** | **Tanda tangan:** | **Tanda tangan:** |

<br>

**Dokumen:** Form UAT Sistem E-Tiket IT Support  
**Status dokumen:** Draft untuk pengujian penerimaan pengguna
