<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rekap Laporan Kerja IT Support</title>
<style>
*{box-sizing:border-box}
body{
  margin:0;font-family:Arial,Helvetica,sans-serif;background:#eef3f7;color:#172033;
}
.page{
  width:1280px;margin:25px auto;background:#fff;padding:28px;
  border-radius:16px;box-shadow:0 10px 35px rgba(15,23,42,.10);
}
.header{
  display:flex;align-items:center;gap:18px;padding-bottom:18px;
  border-bottom:3px solid #0f5132;
}
.logo{
  width:78px;height:78px;border:2px solid #0f5132;border-radius:12px;
  display:flex;align-items:center;justify-content:center;text-align:center;
  color:#0f5132;font-size:10px;font-weight:bold;background:#f0fdf4;
  overflow:hidden;
}
.logo img{width:100%;height:100%;object-fit:contain}
.title{flex:1}
.title h1{margin:0;color:#0f5132;font-size:27px}
.title p{margin:6px 0 0;color:#64748b;font-size:13px}
.header-right{text-align:right;font-size:12px;color:#475569}
.controls{
  margin-top:22px;padding:18px;background:#f8fafc;border:1px solid #dbe4ec;
  border-radius:12px;display:flex;align-items:end;gap:12px;flex-wrap:wrap;
}
.control{display:flex;flex-direction:column;gap:6px}
.control label{font-size:11px;font-weight:bold;color:#475569}
select,input,button{
  height:38px;border:1px solid #cbd5e1;border-radius:7px;padding:0 12px;
  font-size:12px;background:white;
}
button{
  background:#0f5132;color:white;border:none;font-weight:bold;cursor:pointer;
}
button:hover{background:#0b3d25}
.btn-reset{background:#64748b}
.summary{
  display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:18px 0;
}
.card{
  border:1px solid #dbe4ec;border-radius:10px;padding:16px;background:#fff;
}
.card .label{font-size:11px;color:#64748b}
.card .number{font-size:25px;font-weight:bold;color:#0f5132;margin-top:7px}
.section-title{
  background:#0f5132;color:#fff;padding:11px 14px;border-radius:7px;
  font-size:14px;font-weight:bold;margin:20px 0 10px;
}
table{width:100%;border-collapse:collapse;table-layout:fixed}
th,td{
  border:1px solid #cbd5e1;padding:9px 8px;font-size:11px;
  vertical-align:middle;
}
th{background:#dcefe5;color:#123c2a;text-align:center}
td.center{text-align:center}
.status{
  display:inline-block;padding:4px 9px;border-radius:20px;
  font-size:10px;font-weight:bold;
}
.done{background:#dcfce7;color:#166534}
.progress{background:#fef3c7;color:#92400e}
.pending{background:#fee2e2;color:#991b1b}
.footer{
  margin-top:22px;border-top:1px solid #cbd5e1;padding-top:10px;
  display:flex;justify-content:space-between;font-size:10px;color:#64748b;
}
.no-data{
  text-align:center;padding:25px;color:#64748b;display:none;
}
@media print{
  body{background:#fff}.page{margin:0;width:100%;box-shadow:none}
  .controls{display:none}
}
</style>
</head>
<body>

<div class="page">
  <header class="header">
    <div class="logo" id="logoBox">
      <span>LOGO<br>PERUSAHAAN</span>
      <!-- Ganti dengan logo perusahaan:
      <img src="logo-perusahaan.png" alt="Logo Perusahaan">
      -->
    </div>
    <div class="title">
      <h1>REKAPAN LAPORAN KERJA IT SUPPORT</h1>
      <p>Monitoring pekerjaan, kendala, penyelesaian, dan status tiket</p>
    </div>
    <div class="header-right">
      <strong>PERIODE AKTIF</strong><br>
      <span id="periodText">Semua Data</span>
    </div>
  </header>

  <section class="controls">
    <div class="control">
      <label>PERIODE</label>
      <select id="period">
        <option value="all">Semua Data</option>
        <option value="week">Minggu Ini</option>
        <option value="month">Bulan Ini</option>
        <option value="custom">Custom</option>
      </select>
    </div>

    <div class="control" id="startWrap" style="display:none">
      <label>TANGGAL MULAI</label>
      <input type="date" id="startDate">
    </div>

    <div class="control" id="endWrap" style="display:none">
      <label>TANGGAL AKHIR</label>
      <input type="date" id="endDate">
    </div>

    <div class="control">
      <label>STATUS</label>
      <select id="statusFilter">
        <option value="all">Semua Status</option>
        <option value="Selesai">Selesai</option>
        <option value="Proses">Proses</option>
        <option value="Pending">Pending</option>
      </select>
    </div>

    <div class="control">
      <label>UNIT / RUANGAN</label>
      <select id="unitFilter">
        <option value="all">Semua Unit</option>
      </select>
    </div>

    <button onclick="applyFilter()">Terapkan Filter</button>
    <button class="btn-reset" onclick="resetFilter()">Reset</button>
  </section>

  <section class="summary">
    <div class="card"><div class="label">TOTAL LAPORAN</div><div class="number" id="total">0</div></div>
    <div class="card"><div class="label">SELESAI</div><div class="number" id="selesai">0</div></div>
    <div class="card"><div class="label">DALAM PROSES</div><div class="number" id="proses">0</div></div>
    <div class="card"><div class="label">PENDING</div><div class="number" id="pending">0</div></div>
    <div class="card"><div class="label">TINGKAT PENYELESAIAN</div><div class="number" id="rate">0%</div></div>
  </section>

  <div class="section-title">REKAP DATA LAPORAN</div>
  <table>
    <thead>
      <tr>
        <th style="width:5%">No</th>
        <th style="width:10%">Tanggal</th>
        <th style="width:15%">Unit / Ruangan</th>
        <th style="width:12%">Pelapor</th>
        <th style="width:12%">Petugas IT</th>
        <th style="width:11%">Kategori</th>
        <th style="width:17%">Kendala</th>
        <th style="width:16%">Penyelesaian</th>
        <th style="width:9%">Status</th>
      </tr>
    </thead>
    <tbody id="reportBody"></tbody>
  </table>
  <div class="no-data" id="noData">Tidak ada data untuk filter yang dipilih.</div>

  <div class="section-title">REKAP PER KATEGORI</div>
  <table>
    <thead>
      <tr>
        <th>Kategori</th><th>Total</th><th>Selesai</th><th>Proses</th><th>Pending</th>
      </tr>
    </thead>
    <tbody id="categoryBody"></tbody>
  </table>

  <div class="footer">
    <span>Template Rekapan IT Support</span>
    <span id="updated">Terakhir diperbarui: -</span>
  </div>
</div>

<script>
const reports = [
  {date:"2026-08-23",unit:"Pendaftaran",pelapor:"Budi",petugas:"Agustinus",kategori:"Network",kendala:"Komputer tidak terhubung jaringan",penyelesaian:"Pemeriksaan kabel dan konfigurasi IP",status:"Selesai"},
  {date:"2026-08-22",unit:"Farmasi",pelapor:"Sinta",petugas:"Agustinus",kategori:"Printer",kendala:"Printer tidak dapat mencetak",penyelesaian:"Pemeriksaan driver dan koneksi printer",status:"Selesai"},
  {date:"2026-08-21",unit:"IGD",pelapor:"Andi",petugas:"Riko",kategori:"Hardware",kendala:"Monitor tidak menampilkan gambar",penyelesaian:"Pemeriksaan kabel dan perangkat monitor",status:"Proses"},
  {date:"2026-08-18",unit:"Laboratorium",pelapor:"Maya",petugas:"Riko",kategori:"Software",kendala:"Aplikasi tidak dapat dibuka",penyelesaian:"Pemeriksaan aplikasi dan konfigurasi",status:"Pending"},
  {date:"2026-08-10",unit:"Rawat Inap",pelapor:"Doni",petugas:"Agustinus",kategori:"Network",kendala:"Wi-Fi tidak stabil",penyelesaian:"Pemeriksaan access point dan koneksi",status:"Selesai"}
];

const $ = id => document.getElementById(id);

function formatDate(s){
  const d=new Date(s+"T00:00:00");
  return d.toLocaleDateString("id-ID",{day:"2-digit",month:"2-digit",year:"numeric"});
}
function monday(d){
  const x=new Date(d); const day=x.getDay() || 7;
  x.setDate(x.getDate()-day+1); x.setHours(0,0,0,0); return x;
}
function render(data){
  $("total").textContent=data.length;
  $("selesai").textContent=data.filter(x=>x.status==="Selesai").length;
  $("proses").textContent=data.filter(x=>x.status==="Proses").length;
  $("pending").textContent=data.filter(x=>x.status==="Pending").length;
  $("rate").textContent=data.length ? Math.round(data.filter(x=>x.status==="Selesai").length/data.length*100)+"%" : "0%";

  const body=$("reportBody"); body.innerHTML="";
  data.forEach((r,i)=>{
    const cls=r.status==="Selesai"?"done":r.status==="Proses"?"progress":"pending";
    body.innerHTML += `<tr>
      <td class="center">${i+1}</td><td class="center">${formatDate(r.date)}</td>
      <td>${r.unit}</td><td>${r.pelapor}</td><td>${r.petugas}</td>
      <td>${r.kategori}</td><td>${r.kendala}</td><td>${r.penyelesaian}</td>
      <td class="center"><span class="status ${cls}">${r.status.toUpperCase()}</span></td>
    </tr>`;
  });
  $("noData").style.display=data.length?"none":"block";

  const cats=[...new Set(data.map(x=>x.kategori))];
  $("categoryBody").innerHTML=cats.map(c=>{
    const a=data.filter(x=>x.kategori===c);
    return `<tr><td>${c}</td><td class="center">${a.length}</td>
      <td class="center">${a.filter(x=>x.status==="Selesai").length}</td>
      <td class="center">${a.filter(x=>x.status==="Proses").length}</td>
      <td class="center">${a.filter(x=>x.status==="Pending").length}</td></tr>`;
  }).join("") || `<tr><td colspan="5" class="center">Tidak ada data</td></tr>`;
}

function fillUnits(){
  const units=[...new Set(reports.map(x=>x.unit))].sort();
  $("unitFilter").innerHTML='<option value="all">Semua Unit</option>'+units.map(u=>`<option>${u}</option>`).join("");
}

function applyFilter(){
  const period=$("period").value, status=$("statusFilter").value, unit=$("unitFilter").value;
  const now=new Date(); now.setHours(0,0,0,0);
  let start=null,end=null,label="Semua Data";

  if(period==="week"){
    start=monday(now); end=new Date(start); end.setDate(end.getDate()+6); label=`Minggu ${formatDate(start.toISOString().slice(0,10))} - ${formatDate(end.toISOString().slice(0,10))}`;
  }else if(period==="month"){
    start=new Date(now.getFullYear(),now.getMonth(),1); end=new Date(now.getFullYear(),now.getMonth()+1,0);
    label=now.toLocaleDateString("id-ID",{month:"long",year:"numeric"});
  }else if(period==="custom"){
    start=$("startDate").value?new Date($("startDate").value+"T00:00:00"):null;
    end=$("endDate").value?new Date($("endDate").value+"T23:59:59"):null;
    label=(start&&end)?`${formatDate($("startDate").value)} - ${formatDate($("endDate").value)}`:"Custom";
  }

  const data=reports.filter(r=>{
    const d=new Date(r.date+"T12:00:00");
    return (!start||d>=start)&&(!end||d<=end)&&(status==="all"||r.status===status)&&(unit==="all"||r.unit===unit);
  });
  $("periodText").textContent=label;
  render(data);
  $("updated").textContent="Terakhir diperbarui: "+new Date().toLocaleString("id-ID");
}

function resetFilter(){
  $("period").value="all"; $("statusFilter").value="all"; $("unitFilter").value="all";
  $("startDate").value=""; $("endDate").value="";
  toggleCustom(); applyFilter();
}
function toggleCustom(){
  const show=$("period").value==="custom";
  $("startWrap").style.display=show?"flex":"none";
  $("endWrap").style.display=show?"flex":"none";
}
$("period").addEventListener("change",toggleCustom);

fillUnits(); render(reports);
</script>
</body>
</html>
