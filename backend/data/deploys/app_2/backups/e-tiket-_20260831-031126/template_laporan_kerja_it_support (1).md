<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Laporan Kerja IT Support</title>
<style>
  *{box-sizing:border-box}
  body{
    margin:0;
    font-family:Arial,Helvetica,sans-serif;
    background:#eef3f7;
    color:#1f2937;
  }
  .page{
    width:1200px;
    margin:30px auto;
    background:#fff;
    padding:32px;
    border-radius:14px;
    box-shadow:0 8px 30px rgba(15,23,42,.10);
  }
  .header{
    display:flex;
    justify-content:space-between;
    align-items:center;
    border-bottom:3px solid #0f5132;
    padding-bottom:18px;
    margin-bottom:22px;
  }
  .brand h1{
    margin:0 0 6px;
    color:#0f5132;
    font-size:26px;
  }
  .brand p{margin:0;color:#64748b;font-size:13px}
  .report-no{
    text-align:right;
    font-size:13px;
    line-height:1.7;
  }
  .report-no strong{color:#0f5132}
  .section-title{
    background:#0f5132;
    color:white;
    padding:10px 14px;
    border-radius:7px;
    font-size:14px;
    font-weight:bold;
    margin:20px 0 10px;
  }
  table{
    width:100%;
    border-collapse:collapse;
    table-layout:fixed;
  }
  th,td{
    border:1px solid #cbd5e1;
    padding:9px 10px;
    font-size:12px;
    vertical-align:top;
  }
  th{
    background:#dcefe5;
    color:#123c2a;
    text-align:center;
    font-weight:700;
  }
  .label{width:16%;font-weight:bold;background:#f8fafc}
  .value{width:34%}
  .status{
    display:inline-block;
    padding:4px 10px;
    border-radius:20px;
    font-weight:bold;
    font-size:11px;
  }
  .done{background:#dcfce7;color:#166534}
  .progress{background:#fef3c7;color:#92400e}
  .pending{background:#fee2e2;color:#991b1b}
  .photo-grid{
    display:grid;
    grid-template-columns:1fr 1fr;
    gap:14px;
  }
  .photo-box{
    height:230px;
    border:2px dashed #94a3b8;
    border-radius:9px;
    background:#f8fafc;
    display:flex;
    align-items:center;
    justify-content:center;
    color:#64748b;
    text-align:center;
    overflow:hidden;
  }
  .photo-box img{width:100%;height:100%;object-fit:cover}
  .photo-caption{
    margin-top:6px;
    text-align:center;
    font-size:11px;
    color:#64748b;
  }
  .signature{
    height:90px;
    border:1px solid #cbd5e1;
    background:#fff;
  }
  .footer{
    margin-top:24px;
    display:flex;
    justify-content:space-between;
    font-size:10px;
    color:#64748b;
    border-top:1px solid #cbd5e1;
    padding-top:10px;
  }
  .excel-note{
    margin-top:18px;
    padding:12px 14px;
    background:#f0fdf4;
    border-left:4px solid #0f5132;
    font-size:11px;
    line-height:1.6;
  }
  @media print{
    body{background:#fff}
    .page{margin:0;width:100%;box-shadow:none;border-radius:0}
  }
</style>
</head>
<body>

<div class="page">
  <div class="header">
    <div class="brand">
      <h1>LAPORAN KERJA IT SUPPORT</h1>
      <p>Dokumentasi pekerjaan, penanganan kendala, dan hasil penyelesaian</p>
    </div>
    <div class="report-no">
      <div><strong>No. Laporan:</strong> IT-2026-001</div>
      <div><strong>Tanggal:</strong> 23 Agustus 2026</div>
    </div>
  </div>

  <div class="section-title">1. INFORMASI PEKERJAAN</div>
  <table>
    <tr>
      <td class="label">Unit / Ruangan</td><td class="value">Contoh: Ruang Pendaftaran</td>
      <td class="label">Petugas IT</td><td class="value">Nama Petugas</td>
    </tr>
    <tr>
      <td class="label">Pelapor</td><td class="value">Nama Pelapor</td>
      <td class="label">Tanggal / Jam</td><td class="value">23/08/2026 - 09:30</td>
    </tr>
    <tr>
      <td class="label">Kategori</td><td class="value">Hardware / Software / Network / Printer</td>
      <td class="label">Prioritas</td><td class="value">Normal</td>
    </tr>
  </table>

  <div class="section-title">2. DETAIL KENDALA & PENYELESAIAN</div>
  <table>
    <tr>
      <th style="width:6%">No</th>
      <th style="width:20%">Kendala</th>
      <th style="width:25%">Tindakan / Penyelesaian</th>
      <th style="width:18%">Hasil</th>
      <th style="width:13%">Status</th>
      <th style="width:18%">Keterangan</th>
    </tr>
    <tr>
      <td style="text-align:center">1</td>
      <td>Komputer tidak dapat terhubung ke jaringan.</td>
      <td>Pemeriksaan kabel LAN, konfigurasi IP, dan pengujian koneksi.</td>
      <td>Koneksi jaringan kembali normal.</td>
      <td style="text-align:center"><span class="status done">SELESAI</span></td>
      <td>Tidak ada kendala lanjutan.</td>
    </tr>
    <tr>
      <td style="text-align:center">2</td>
      <td>Printer tidak dapat melakukan cetak.</td>
      <td>Pemeriksaan driver dan koneksi printer.</td>
      <td>Printer dapat digunakan kembali.</td>
      <td style="text-align:center"><span class="status done">SELESAI</span></td>
      <td>Monitoring dilakukan.</td>
    </tr>
  </table>

  <div class="section-title">3. DOKUMENTASI FOTO</div>
  <div class="photo-grid">
    <div>
      <div class="photo-box">FOTO SEBELUM PEKERJAAN<br><small>Tempel / upload foto di area ini</small></div>
      <div class="photo-caption">Dokumentasi kondisi sebelum penanganan</div>
    </div>
    <div>
      <div class="photo-box">FOTO SESUDAH PEKERJAAN<br><small>Tempel / upload foto di area ini</small></div>
      <div class="photo-caption">Dokumentasi kondisi setelah penanganan</div>
    </div>
  </div>

  <div class="section-title">4. VERIFIKASI & PERSETUJUAN</div>
  <table>
    <tr>
      <th>Teknisi / IT Support</th>
      <th>Pelapor / Unit</th>
      <th>Atasan / Supervisor</th>
    </tr>
    <tr>
      <td class="signature"></td>
      <td class="signature"></td>
      <td class="signature"></td>
    </tr>
    <tr>
      <td style="text-align:center">Nama & Tanda Tangan</td>
      <td style="text-align:center">Nama & Tanda Tangan</td>
      <td style="text-align:center">Nama & Tanda Tangan</td>
    </tr>
  </table>

  <div class="excel-note">
    <strong>Patokan Export Excel:</strong> struktur data dibuat mengikuti kolom
    No. Laporan, Tanggal, Unit/Ruangan, Pelapor, Petugas IT, Kategori, Prioritas,
    Kendala, Tindakan/Penyelesaian, Hasil, Status, Keterangan, Foto Sebelum,
    Foto Sesudah, dan Verifikasi. Untuk Excel, setiap laporan dapat dibuat menjadi
    satu baris data; dokumentasi foto dapat ditempatkan sebagai hyperlink atau gambar
    pada kolom terpisah.
  </div>

  <div class="footer">
    <span>Dokumen Laporan Kerja IT Support</span>
    <span>Template siap dijadikan acuan Excel</span>
  </div>
</div>

</body>
</html>
