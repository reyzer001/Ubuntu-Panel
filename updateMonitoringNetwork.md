Di bawah ini versi **V0.2**: semua menu sidebar sudah aktif dan bisa dibuka. Masih **1 file HTML**, jadi tinggal simpan sebagai `index.html` lalu buka di browser.

Yang sudah ada:

* Dashboard
* Services
* Processes
* Logs
* Storage
* Network
* Docker
* Firewall
* Users
* Terminal
* Server selector
* Responsive sidebar
* Search/filter tabel
* Start/Stop/Restart service
* Kill process prototype
* Docker action
* Firewall toggle
* Add user prototype
* Terminal simulasi
* Toast notification
* Realtime metric simulation

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ubuntu Server Manager</title>

<style>
:root{
  --bg:#080c11;
  --sidebar:#0c1117;
  --panel:#111821;
  --panel2:#151e28;
  --panel3:#1a2430;
  --border:#24303d;
  --text:#eef3f8;
  --muted:#8794a4;
  --muted2:#5f6c7c;

  --green:#22c55e;
  --red:#ef4444;
  --orange:#f59e0b;
  --blue:#3b82f6;
  --purple:#8b5cf6;
  --cyan:#06b6d4;

  --radius:14px;
}

*{
  box-sizing:border-box;
  margin:0;
  padding:0;
}

body{
  font-family:
    Inter,
    ui-sans-serif,
    system-ui,
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    sans-serif;
  background:var(--bg);
  color:var(--text);
  min-height:100vh;
}

button,
input,
select,
textarea{
  font:inherit;
}

button{
  cursor:pointer;
}

.app{
  min-height:100vh;
}

/* =========================================================
   SIDEBAR
========================================================= */

.sidebar{
  position:fixed;
  left:0;
  top:0;
  bottom:0;
  width:250px;
  background:var(--sidebar);
  border-right:1px solid var(--border);
  padding:20px 14px;
  overflow-y:auto;
  z-index:50;
}

.logo{
  display:flex;
  align-items:center;
  gap:11px;
  padding:4px 10px 22px;
  font-size:17px;
  font-weight:750;
}

.logo-icon{
  width:38px;
  height:38px;
  border-radius:10px;
  display:grid;
  place-items:center;
  background:#e95420;
  color:#fff;
  font-weight:900;
}

.server-selector{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:12px;
  padding:13px;
  margin-bottom:20px;
}

.server-selector-label{
  color:var(--muted2);
  font-size:9px;
  font-weight:700;
  letter-spacing:.12em;
  text-transform:uppercase;
}

.server-selector select{
  width:100%;
  margin-top:7px;
  padding:9px;
  background:var(--panel2);
  color:var(--text);
  border:1px solid var(--border);
  border-radius:8px;
  outline:none;
}

.server-online{
  margin-top:10px;
  display:flex;
  align-items:center;
  gap:7px;
  color:var(--green);
  font-size:11px;
}

.server-online-dot{
  width:7px;
  height:7px;
  border-radius:50%;
  background:var(--green);
  box-shadow:0 0 8px var(--green);
}

.nav-section{
  margin-top:17px;
}

.nav-section-title{
  color:#566171;
  font-size:9px;
  letter-spacing:.12em;
  font-weight:800;
  padding:0 10px 7px;
  text-transform:uppercase;
}

.nav-item{
  width:100%;
  display:flex;
  align-items:center;
  gap:11px;
  color:#909cab;
  background:transparent;
  border:0;
  padding:10px 12px;
  border-radius:9px;
  text-align:left;
  margin-bottom:2px;
  transition:.15s;
}

.nav-item:hover{
  background:#141c25;
  color:#fff;
}

.nav-item.active{
  background:#17202a;
  color:#fff;
  box-shadow:inset 2px 0 0 #e95420;
}

.nav-icon{
  width:18px;
  text-align:center;
  opacity:.9;
}

.nav-label{
  font-size:12px;
}

/* =========================================================
   MAIN
========================================================= */

.main{
  margin-left:250px;
  min-height:100vh;
  padding:26px;
}

.topbar{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:15px;
  margin-bottom:24px;
}

.page-title h1{
  font-size:24px;
  font-weight:760;
}

.page-title p{
  margin-top:5px;
  color:var(--muted);
  font-size:12px;
}

.top-actions{
  display:flex;
  gap:8px;
}

.btn{
  border:1px solid var(--border);
  background:var(--panel);
  color:#d7dee7;
  padding:9px 13px;
  border-radius:8px;
  font-size:11px;
  transition:.15s;
}

.btn:hover{
  background:var(--panel2);
}

.btn.primary{
  background:#1b4d90;
  border-color:#2865b2;
  color:#fff;
}

.btn.success{
  color:#9df2b8;
  border-color:#1c6636;
  background:#102118;
}

.btn.warning{
  color:#ffd58a;
  border-color:#73520d;
  background:#241b09;
}

.btn.danger{
  color:#ffadad;
  border-color:#6b2525;
  background:#241112;
}

/* =========================================================
   COMMON CARDS
========================================================= */

.card{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:var(--radius);
  padding:18px;
}

.card-header{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:12px;
  margin-bottom:18px;
}

.card-title{
  font-size:14px;
  font-weight:700;
}

.card-subtitle{
  margin-top:4px;
  color:var(--muted);
  font-size:11px;
}

.grid{
  display:grid;
  gap:16px;
}

.grid-2{
  grid-template-columns:repeat(2,minmax(0,1fr));
}

.grid-3{
  grid-template-columns:repeat(3,minmax(0,1fr));
}

.grid-4{
  grid-template-columns:repeat(4,minmax(0,1fr));
}

/* =========================================================
   DASHBOARD
========================================================= */

.health-card{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:20px;
  padding:18px 20px;
  background:linear-gradient(135deg,#0f1b17,#101720);
  border:1px solid #21422c;
  border-radius:14px;
  margin-bottom:16px;
}

.health-left{
  display:flex;
  align-items:center;
  gap:13px;
}

.health-icon{
  width:43px;
  height:43px;
  display:grid;
  place-items:center;
  border-radius:11px;
  background:#11251a;
  color:var(--green);
  font-size:20px;
}

.health-title{
  font-size:14px;
  font-weight:700;
}

.health-desc{
  margin-top:4px;
  color:var(--muted);
  font-size:11px;
}

.health-score{
  text-align:right;
}

.health-score strong{
  display:block;
  font-size:24px;
  color:var(--green);
}

.health-score span{
  color:var(--muted);
  font-size:10px;
}

.stat-card{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:14px;
  padding:17px;
}

.stat-top{
  display:flex;
  justify-content:space-between;
  color:var(--muted);
  font-size:11px;
}

.stat-icon{
  width:30px;
  height:30px;
  display:grid;
  place-items:center;
  background:var(--panel2);
  border-radius:8px;
}

.stat-value{
  margin-top:14px;
  font-size:26px;
  font-weight:760;
}

.stat-bottom{
  margin-top:7px;
  display:flex;
  justify-content:space-between;
  color:var(--muted);
  font-size:10px;
}

.positive{
  color:var(--green)!important;
}

.warning-text{
  color:var(--orange)!important;
}

.negative{
  color:var(--red)!important;
}

.chart{
  height:230px;
  border-radius:10px;
  overflow:hidden;
  position:relative;
  background:
    linear-gradient(to bottom,
      transparent 24%,
      #202a35 25%,
      transparent 26%
    ),
    linear-gradient(to bottom,
      transparent 49%,
      #202a35 50%,
      transparent 51%
    ),
    linear-gradient(to bottom,
      transparent 74%,
      #202a35 75%,
      transparent 76%
    );
}

.chart svg{
  width:100%;
  height:100%;
}

.chart-labels{
  display:flex;
  justify-content:space-between;
  color:var(--muted2);
  font-size:9px;
  margin-top:5px;
}

/* =========================================================
   TABLES
========================================================= */

.table-wrap{
  overflow:auto;
}

table{
  width:100%;
  border-collapse:collapse;
}

th,
td{
  padding:12px 10px;
  text-align:left;
  border-bottom:1px solid var(--border);
  white-space:nowrap;
}

th{
  color:var(--muted2);
  font-size:10px;
  font-weight:750;
  text-transform:uppercase;
  letter-spacing:.04em;
}

td{
  color:#d9e0e8;
  font-size:11px;
}

tr:hover td{
  background:#141c24;
}

.status{
  display:inline-flex;
  align-items:center;
  padding:4px 8px;
  border-radius:999px;
  font-size:9px;
  font-weight:750;
}

.status.running{
  color:#9df2b8;
  background:#102118;
}

.status.stopped{
  color:#ffabab;
  background:#241112;
}

.status.warning{
  color:#ffd58a;
  background:#271f0d;
}

.status.info{
  color:#9fc5ff;
  background:#111f34;
}

.row-actions{
  display:flex;
  gap:5px;
}

.action-btn{
  padding:6px 8px;
  border-radius:6px;
  border:1px solid var(--border);
  background:var(--panel2);
  color:#cdd6e0;
  font-size:9px;
}

.action-btn:hover{
  background:var(--panel3);
}

/* =========================================================
   SEARCH
========================================================= */

.toolbar{
  display:flex;
  justify-content:space-between;
  gap:10px;
  margin-bottom:15px;
  flex-wrap:wrap;
}

.search{
  min-width:240px;
  padding:9px 11px;
  border-radius:8px;
  border:1px solid var(--border);
  background:var(--panel2);
  color:var(--text);
  outline:none;
}

.search:focus{
  border-color:#376da8;
}

/* =========================================================
   STORAGE
========================================================= */

.storage-item{
  margin-bottom:20px;
}

.storage-head{
  display:flex;
  justify-content:space-between;
  font-size:11px;
  margin-bottom:8px;
}

.storage-head span:last-child{
  color:var(--muted);
}

.progress{
  height:8px;
  border-radius:999px;
  background:#202a34;
  overflow:hidden;
}

.progress-bar{
  height:100%;
  border-radius:inherit;
}

.bar-blue{background:var(--blue)}
.bar-green{background:var(--green)}
.bar-orange{background:var(--orange)}
.bar-purple{background:var(--purple)}
.bar-red{background:var(--red)}

/* =========================================================
   LOGS
========================================================= */

.log-list{
  display:flex;
  flex-direction:column;
  gap:8px;
}

.log-item{
  display:grid;
  grid-template-columns:75px 70px 100px 1fr;
  gap:10px;
  align-items:center;
  padding:11px 12px;
  background:#131a22;
  border:1px solid var(--border);
  border-radius:9px;
  font-size:10px;
}

.log-time{
  color:var(--muted2);
}

.log-level{
  font-weight:750;
}

.log-source{
  color:#9eabb9;
}

.log-message{
  color:#d7dee6;
}

.level-info{color:#7fb2ff}
.level-warn{color:#ffd277}
.level-error{color:#ff8f8f}

/* =========================================================
   TERMINAL
========================================================= */

.terminal{
  background:#060a0d;
  border:1px solid #202a35;
  border-radius:12px;
  overflow:hidden;
  box-shadow:0 15px 40px rgba(0,0,0,.25);
}

.terminal-head{
  height:35px;
  display:flex;
  align-items:center;
  gap:7px;
  padding:0 12px;
  background:#11171d;
  border-bottom:1px solid #202a35;
}

.term-dot{
  width:9px;
  height:9px;
  border-radius:50%;
}

.term-red{background:#ff5f56}
.term-yellow{background:#ffbd2e}
.term-green{background:#27c93f}

.terminal-body{
  padding:18px;
  min-height:390px;
  font-family:
    "SFMono-Regular",
    Consolas,
    monospace;
  font-size:11px;
  line-height:1.8;
  color:#dce8d7;
}

.term-prompt{
  color:#6ee28a;
}

.term-output{
  color:#aab6c3;
}

.term-input-row{
  display:flex;
  align-items:center;
  gap:8px;
}

.term-input{
  flex:1;
  background:transparent;
  border:0;
  outline:none;
  color:#fff;
  font-family:inherit;
  font-size:11px;
}

/* =========================================================
   EMPTY / INFO
========================================================= */

.info-grid{
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:10px;
}

.info-item{
  background:#141c24;
  border:1px solid var(--border);
  border-radius:10px;
  padding:12px;
}

.info-label{
  color:var(--muted2);
  font-size:9px;
  text-transform:uppercase;
  letter-spacing:.05em;
}

.info-value{
  margin-top:5px;
  font-size:12px;
  font-weight:600;
}

/* =========================================================
   TOAST
========================================================= */

.toast{
  position:fixed;
  right:20px;
  bottom:20px;
  z-index:100;
  background:#131a22;
  border:1px solid var(--border);
  color:#e7eef6;
  padding:11px 14px;
  border-radius:9px;
  box-shadow:0 15px 30px rgba(0,0,0,.3);
  font-size:11px;
  opacity:0;
  transform:translateY(10px);
  pointer-events:none;
  transition:.2s;
}

.toast.show{
  opacity:1;
  transform:translateY(0);
}

/* =========================================================
   MOBILE
========================================================= */

@media(max-width:1100px){
  .grid-4{
    grid-template-columns:repeat(2,1fr);
  }

  .grid-3{
    grid-template-columns:1fr 1fr;
  }
}

@media(max-width:900px){
  .sidebar{
    width:70px;
    padding:14px 8px;
  }

  .logo span,
  .server-selector,
  .nav-section-title,
  .nav-label{
    display:none;
  }

  .nav-item{
    justify-content:center;
  }

  .main{
    margin-left:70px;
    padding:18px;
  }

  .grid-2,
  .grid-3{
    grid-template-columns:1fr;
  }
}

@media(max-width:600px){
  .grid-4{
    grid-template-columns:1fr;
  }

  .topbar{
    flex-direction:column;
    align-items:flex-start;
  }

  .health-card{
    flex-direction:column;
    align-items:flex-start;
  }

  .log-item{
    grid-template-columns:1fr;
    gap:4px;
  }
}
</style>
</head>

<body>

<div class="app">

  <!-- =====================================================
       SIDEBAR
  ====================================================== -->

  <aside class="sidebar">

    <div class="logo">
      <div class="logo-icon">U</div>
      <span>Server Manager</span>
    </div>

    <div class="server-selector">

      <div class="server-selector-label">
        Active Server
      </div>

      <select id="serverSelect">
        <option>ubuntu-prod-01</option>
        <option>ubuntu-dev-01</option>
        <option>ubuntu-db-01</option>
      </select>

      <div class="server-online">
        <span class="server-online-dot"></span>
        Online
      </div>

    </div>

    <div class="nav-section">

      <div class="nav-section-title">
        Overview
      </div>

      <button class="nav-item active" data-page="dashboard">
        <span class="nav-icon">▦</span>
        <span class="nav-label">Dashboard</span>
      </button>

    </div>

    <div class="nav-section">

      <div class="nav-section-title">
        System
      </div>

      <button class="nav-item" data-page="services">
        <span class="nav-icon">◉</span>
        <span class="nav-label">Services</span>
      </button>

      <button class="nav-item" data-page="processes">
        <span class="nav-icon">⌁</span>
        <span class="nav-label">Processes</span>
      </button>

      <button class="nav-item" data-page="logs">
        <span class="nav-icon">▤</span>
        <span class="nav-label">Logs</span>
      </button>

    </div>

    <div class="nav-section">

      <div class="nav-section-title">
        Infrastructure
      </div>

      <button class="nav-item" data-page="storage">
        <span class="nav-icon">◫</span>
        <span class="nav-label">Storage</span>
      </button>

      <button class="nav-item" data-page="network">
        <span class="nav-icon">⇄</span>
        <span class="nav-label">Network</span>
      </button>

      <button class="nav-item" data-page="docker">
        <span class="nav-icon">⬡</span>
        <span class="nav-label">Docker</span>
      </button>

    </div>

    <div class="nav-section">

      <div class="nav-section-title">
        Security
      </div>

      <button class="nav-item" data-page="firewall">
        <span class="nav-icon">◈</span>
        <span class="nav-label">Firewall</span>
      </button>

      <button class="nav-item" data-page="users">
        <span class="nav-icon">♙</span>
        <span class="nav-label">Users</span>
      </button>

      <button class="nav-item" data-page="terminal">
        <span class="nav-icon">⌘</span>
        <span class="nav-label">Terminal</span>
      </button>

    </div>

  </aside>


  <!-- =====================================================
       MAIN
  ====================================================== -->

  <main class="main">

    <div id="pageContainer"></div>

  </main>

</div>


<div class="toast" id="toast"></div>


<script>

/* =========================================================
   DATA
========================================================= */

const state = {

  page:"dashboard",

  cpu:24,
  ram:63,
  load:1.42,

  services:[
    {
      name:"nginx",
      description:"Web Server",
      status:"running",
      uptime:"14d 08h"
    },
    {
      name:"postgresql",
      description:"Database",
      status:"running",
      uptime:"14d 08h"
    },
    {
      name:"docker",
      description:"Container Engine",
      status:"running",
      uptime:"14d 08h"
    },
    {
      name:"redis",
      description:"Cache",
      status:"running",
      uptime:"6d 03h"
    },
    {
      name:"ssh",
      description:"Remote Access",
      status:"running",
      uptime:"14d 08h"
    },
    {
      name:"cron",
      description:"Scheduled Tasks",
      status:"running",
      uptime:"14d 08h"
    },
    {
      name:"apache2",
      description:"Apache Web Server",
      status:"stopped",
      uptime:"—"
    }
  ],

  processes:[
    ["1021","mysql","18.4","2.4 GB","mysqld"],
    ["1821","www-data","11.2","1.2 GB","php-fpm"],
    ["2911","root","4.4","420 MB","dockerd"],
    ["1092","root","2.1","210 MB","systemd"],
    ["8192","www-data","1.7","180 MB","nginx"],
    ["7721","redis","1.1","160 MB","redis-server"]
  ],

  containers:[
    {
      name:"nginx",
      image:"nginx:latest",
      status:"running",
      cpu:"2.3%",
      memory:"120 MB",
      ports:"80, 443"
    },
    {
      name:"postgres",
      image:"postgres:16",
      status:"running",
      cpu:"6.1%",
      memory:"850 MB",
      ports:"5432"
    },
    {
      name:"redis",
      image:"redis:7",
      status:"running",
      cpu:"1.2%",
      memory:"92 MB",
      ports:"6379"
    },
    {
      name:"api",
      image:"my-app:latest",
      status:"running",
      cpu:"4.6%",
      memory:"420 MB",
      ports:"3000"
    }
  ],

  firewall:[
    ["22","TCP","SSH","ALLOW","Anywhere"],
    ["80","TCP","HTTP","ALLOW","Anywhere"],
    ["443","TCP","HTTPS","ALLOW","Anywhere"],
    ["3306","TCP","MySQL","DENY","Anywhere"],
    ["6379","TCP","Redis","DENY","Anywhere"],
    ["5432","TCP","PostgreSQL","DENY","Anywhere"]
  ],

  users:[
    ["root","0","root","/root","/bin/bash","Active"],
    ["ubuntu","1000","sudo","/home/ubuntu","/bin/bash","Active"],
    ["deploy","1001","deploy","/home/deploy","/bin/bash","Active"],
    ["backup","1002","backup","/home/backup","/usr/sbin/nologin","Active"]
  ],

  logs:[
    ["08:51:11","INFO","systemd","nginx service started successfully"],
    ["08:50:42","INFO","backup","Daily backup completed"],
    ["08:48:23","WARN","filesystem","/var filesystem reached 82%"],
    ["08:47:02","INFO","docker","Container api restarted"],
    ["08:45:21","ERROR","sshd","Failed login from 185.24.12.4"],
    ["08:41:14","INFO","ufw","Firewall rules reloaded"],
    ["08:39:57","INFO","cron","Scheduled job completed"],
    ["08:35:02","WARN","memory","Memory usage crossed 70%"]
  ]

};


/* =========================================================
   HELPERS
========================================================= */

const app = document.getElementById("pageContainer");

function toast(message){

  const el =
    document.getElementById("toast");

  el.textContent = message;

  el.classList.add("show");

  clearTimeout(window.toastTimer);

  window.toastTimer =
    setTimeout(()=>{
      el.classList.remove("show");
    },2200);
}


function escapeHtml(value){

  return String(value)
    .replaceAll("&","&amp;")
    .replaceAll("<","&lt;")
    .replaceAll(">","&gt;")
    .replaceAll('"',"&quot;")
    .replaceAll("'","&#039;");
}


function statusBadge(status){

  const map = {
    running:["running","RUNNING"],
    stopped:["stopped","STOPPED"],
    active:["running","ACTIVE"],
    warning:["warning","WARNING"],
    info:["info","INFO"],
    allow:["running","ALLOW"],
    deny:["stopped","DENY"]
  };

  const item =
    map[status] ||
    ["info",status.toUpperCase()];

  return `
    <span class="status ${item[0]}">
      ${item[1]}
    </span>
  `;
}


function updateTopbar(title,subtitle){

  return `
    <div class="topbar">

      <div class="page-title">
        <h1>${title}</h1>
        <p>${subtitle}</p>
      </div>

      <div class="top-actions">
        <button
          class="btn"
          onclick="refreshPage()">
          ↻ Refresh
        </button>
      </div>

    </div>
  `;
}


/* =========================================================
   DASHBOARD PAGE
========================================================= */

function renderDashboard(){

  app.innerHTML = `

    ${updateTopbar(
      "Server Overview",
      "Monitoring ubuntu-prod-01 · Updated just now"
    )}

    <section class="health-card">

      <div class="health-left">

        <div class="health-icon">✓</div>

        <div>
          <div class="health-title">
            Server is healthy
          </div>

          <div class="health-desc">
            No critical issues detected. All important services are running.
          </div>
        </div>

      </div>

      <div class="health-score">
        <strong>98%</strong>
        <span>Health score</span>
      </div>

    </section>


    <section class="grid grid-4">

      <div class="stat-card">

        <div class="stat-top">
          <span>CPU Usage</span>
          <div class="stat-icon">⚡</div>
        </div>

        <div class="stat-value" id="cpuValue">
          ${state.cpu}%
        </div>

        <div class="stat-bottom">
          <span>8 vCPU</span>
          <span class="positive">Normal</span>
        </div>

      </div>


      <div class="stat-card">

        <div class="stat-top">
          <span>Memory</span>
          <div class="stat-icon">▤</div>
        </div>

        <div class="stat-value" id="ramValue">
          ${state.ram}%
        </div>

        <div class="stat-bottom">
          <span>10.1 / 16 GB</span>
          <span class="positive">Normal</span>
        </div>

      </div>


      <div class="stat-card">

        <div class="stat-top">
          <span>Storage</span>
          <div class="stat-icon">▰</div>
        </div>

        <div class="stat-value">71%</div>

        <div class="stat-bottom">
          <span>354 / 500 GB</span>
          <span class="warning-text">Watch</span>
        </div>

      </div>


      <div class="stat-card">

        <div class="stat-top">
          <span>Load Average</span>
          <div class="stat-icon">⌁</div>
        </div>

        <div class="stat-value" id="loadValue">
          ${state.load}
        </div>

        <div class="stat-bottom">
          <span>1 minute</span>
          <span class="positive">Normal</span>
        </div>

      </div>

    </section>


    <div style="height:16px"></div>


    <section class="grid grid-2">

      <div class="card">

        <div class="card-header">

          <div>
            <div class="card-title">
              System Performance
            </div>

            <div class="card-subtitle">
              CPU utilization
            </div>
          </div>

          <select class="btn">
            <option>Last 1 hour</option>
            <option>Last 6 hours</option>
            <option>Last 24 hours</option>
          </select>

        </div>

        <div class="chart">

          <svg viewBox="0 0 1000 240" preserveAspectRatio="none">

            <defs>
              <linearGradient
                id="area"
                x1="0"
                x2="0"
                y1="0"
                y2="1">

                <stop
                  offset="0%"
                  stop-color="#3b82f6"
                  stop-opacity=".3"/>

                <stop
                  offset="100%"
                  stop-color="#3b82f6"
                  stop-opacity="0"/>

              </linearGradient>
            </defs>

            <path
              d="
              M0 190
              C40 170 70 185 110 160
              C150 135 180 165 220 145
              C260 120 300 150 340 130
              C380 110 420 115 460 140
              C500 165 530 125 570 135
              C610 145 650 100 690 118
              C730 135 760 110 800 92
              C840 75 875 115 910 85
              C940 65 970 95 1000 72
              L1000 240 L0 240 Z"
              fill="url(#area)"
            />

            <path
              d="
              M0 190
              C40 170 70 185 110 160
              C150 135 180 165 220 145
              C260 120 300 150 340 130
              C380 110 420 115 460 140
              C500 165 530 125 570 135
              C610 145 650 100 690 118
              C730 135 760 110 800 92
              C840 75 875 115 910 85
              C940 65 970 95 1000 72"
              fill="none"
              stroke="#3b82f6"
              stroke-width="3"
            />

          </svg>

        </div>

        <div class="chart-labels">
          <span>08:00</span>
          <span>08:10</span>
          <span>08:20</span>
          <span>08:30</span>
          <span>08:40</span>
          <span>08:50</span>
        </div>

      </div>


      <div class="card">

        <div class="card-header">

          <div>
            <div class="card-title">
              Critical Services
            </div>

            <div class="card-subtitle">
              systemd services
            </div>
          </div>

          <button
            class="btn"
            onclick="navigate('services')">
            View all
          </button>

        </div>

        <div>

          ${state.services
            .filter(s => ["nginx","postgresql","docker","redis","ssh"]
              .includes(s.name))
            .map(s => `

              <div
                style="
                  display:flex;
                  justify-content:space-between;
                  align-items:center;
                  padding:11px 0;
                  border-bottom:1px solid var(--border);
                ">

                <div>
                  <div style="font-size:11px;font-weight:700">
                    ${escapeHtml(s.name)}
                  </div>

                  <div style="font-size:9px;color:var(--muted);margin-top:2px">
                    ${escapeHtml(s.description)}
                  </div>
                </div>

                ${statusBadge(s.status)}

              </div>

            `).join("")}

        </div>

      </div>

    </section>


    <div style="height:16px"></div>


    <section class="grid grid-3">

      <div class="card">

        <div class="card-header">

          <div>
            <div class="card-title">
              Storage
            </div>

            <div class="card-subtitle">
              Filesystem utilization
            </div>
          </div>

          <button
            class="btn"
            onclick="navigate('storage')">
            Manage
          </button>

        </div>


        ${[
          ["/",71,"bar-blue"],
          ["/var",82,"bar-orange"],
          ["/home",44,"bar-purple"]
        ].map(x => `

          <div class="storage-item">

            <div class="storage-head">
              <span>${x[0]}</span>
              <span>${x[1]}%</span>
            </div>

            <div class="progress">
              <div
                class="progress-bar ${x[2]}"
                style="width:${x[1]}%">
              </div>
            </div>

          </div>

        `).join("")}

      </div>


      <div class="card">

        <div class="card-header">

          <div>
            <div class="card-title">
              Network
            </div>

            <div class="card-subtitle">
              Current traffic
            </div>
          </div>

          <button
            class="btn"
            onclick="navigate('network')">
            Details
          </button>

        </div>

        <div class="info-grid">

          <div class="info-item">
            <div class="info-label">Interface</div>
            <div class="info-value">eth0</div>
          </div>

          <div class="info-item">
            <div class="info-label">IP</div>
            <div class="info-value">192.168.1.20</div>
          </div>

          <div class="info-item">
            <div class="info-label">Download</div>
            <div class="info-value">12.4 MB/s</div>
          </div>

          <div class="info-item">
            <div class="info-label">Upload</div>
            <div class="info-value">4.8 MB/s</div>
          </div>

        </div>

      </div>


      <div class="card">

        <div class="card-header">

          <div>
            <div class="card-title">
              Recent Activity
            </div>

            <div class="card-subtitle">
              Latest server events
            </div>
          </div>

          <button
            class="btn"
            onclick="navigate('logs')">
            Logs
          </button>

        </div>

        ${state.logs.slice(0,4).map(log => `

          <div style="
            display:flex;
            gap:9px;
            margin-bottom:12px;
          ">

            <div
              style="
                width:7px;
                height:7px;
                border-radius:50%;
                margin-top:4px;
                background:${
                  log[1] === "ERROR"
                    ? "var(--red)"
                    : log[1] === "WARN"
                    ? "var(--orange)"
                    : "var(--green)"
                };
              ">
            </div>

            <div>
              <div style="font-size:10px">
                ${escapeHtml(log[3])}
              </div>

              <div style="
                margin-top:3px;
                color:var(--muted);
                font-size:9px;
              ">
                ${escapeHtml(log[0])}
              </div>
            </div>

          </div>

        `).join("")}

      </div>

    </section>

  `;

}


/* =========================================================
   SERVICES
========================================================= */

function renderServices(){

  app.innerHTML = `

    ${updateTopbar(
      "Services",
      "Manage systemd services"
    )}

    <div class="card">

      <div class="toolbar">

        <input
          class="search"
          id="serviceSearch"
          placeholder="Search service..."
          oninput="filterTable('serviceSearch','servicesTable')"
        />

        <button
          class="btn primary"
          onclick="toast('Service scanner started')">
          ↻ Scan Services
        </button>

      </div>

      <div class="table-wrap">

        <table id="servicesTable">

          <thead>
            <tr>
              <th>Service</th>
              <th>Description</th>
              <th>Status</th>
              <th>Uptime</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>

            ${state.services.map((s,i)=>`

              <tr>

                <td>
                  <strong>${escapeHtml(s.name)}</strong>
                </td>

                <td>${escapeHtml(s.description)}</td>

                <td>
                  ${statusBadge(s.status)}
                </td>

                <td>${escapeHtml(s.uptime)}</td>

                <td>

                  <div class="row-actions">

                    <button
                      class="action-btn"
                      onclick="serviceAction(${i},'start')">
                      Start
                    </button>

                    <button
                      class="action-btn"
                      onclick="serviceAction(${i},'restart')">
                      Restart
                    </button>

                    <button
                      class="action-btn"
                      onclick="serviceAction(${i},'stop')">
                      Stop
                    </button>

                  </div>

                </td>

              </tr>

            `).join("")}

          </tbody>

        </table>

      </div>

    </div>
  `;
}


function serviceAction(index,action){

  const service =
    state.services[index];

  if(action === "start"){
    service.status = "running";
    service.uptime = "just now";
  }

  if(action === "stop"){
    service.status = "stopped";
    service.uptime = "—";
  }

  if(action === "restart"){
    service.status = "running";
    service.uptime = "just now";
  }

  toast(
    `${service.name}: ${action} command executed`
  );

  renderServices();
}


/* =========================================================
   PROCESSES
========================================================= */

function renderProcesses(){

  app.innerHTML = `

    ${updateTopbar(
      "Processes",
      "Running processes on Ubuntu"
    )}

    <div class="card">

      <div class="toolbar">

        <input
          class="search"
          id="processSearch"
          placeholder="Search process..."
          oninput="filterTable('processSearch','processTable')"
        />

        <select class="btn">
          <option>Sort by CPU</option>
          <option>Sort by RAM</option>
          <option>PID</option>
        </select>

      </div>

      <div class="table-wrap">

        <table id="processTable">

          <thead>
            <tr>
              <th>PID</th>
              <th>User</th>
              <th>CPU</th>
              <th>Memory</th>
              <th>Command</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>

            ${state.processes.map(p=>`

              <tr>

                <td>${p[0]}</td>
                <td>${p[1]}</td>
                <td>${p[2]}%</td>
                <td>${p[3]}</td>
                <td><strong>${p[4]}</strong></td>

                <td>

                  <button
                    class="action-btn"
                    onclick="killProcess('${p[0]}','${escapeHtml(p[4])}')">
                    Kill
                  </button>

                </td>

              </tr>

            `).join("")}

          </tbody>

        </table>

      </div>

    </div>

  `;
}


function killProcess(pid,name){

  if(
    confirm(
      `Kill process ${name} (PID ${pid})?`
    )
  ){
    toast(`Process ${pid} terminated`);
  }

}


/* =========================================================
   LOGS
========================================================= */

function renderLogs(){

  app.innerHTML = `

    ${updateTopbar(
      "System Logs",
      "Journal and system events"
    )}

    <div class="card">

      <div class="toolbar">

        <input
          class="search"
          id="logSearch"
          placeholder="Search logs..."
          oninput="filterLogs()"
        />

        <div style="display:flex;gap:6px">

          <button
            class="btn"
            onclick="toast('Logs refreshed')">
            ↻ Refresh
          </button>

          <button
            class="btn"
            onclick="toast('Log viewer opened')">
            Export
          </button>

        </div>

      </div>


      <div id="logList" class="log-list">

        ${renderLogItems(state.logs)}

      </div>

    </div>

  `;
}


function renderLogItems(logs){

  return logs.map(log=>`

    <div class="log-item">

      <div class="log-time">
        ${escapeHtml(log[0])}
      </div>

      <div class="
        log-level
        ${
          log[1] === "ERROR"
          ? "level-error"
          : log[1] === "WARN"
          ? "level-warn"
          : "level-info"
        }
      ">
        ${escapeHtml(log[1])}
      </div>

      <div class="log-source">
        ${escapeHtml(log[2])}
      </div>

      <div class="log-message">
        ${escapeHtml(log[3])}
      </div>

    </div>

  `).join("");
}


function filterLogs(){

  const q =
    document
      .getElementById("logSearch")
      .value
      .toLowerCase();

  const filtered =
    state.logs.filter(row =>
      row.join(" ")
        .toLowerCase()
        .includes(q)
    );

  document.getElementById(
    "logList"
  ).innerHTML =
    renderLogItems(filtered);
}


/* =========================================================
   STORAGE
========================================================= */

function renderStorage(){

  app.innerHTML = `

    ${updateTopbar(
      "Storage",
      "Disk and filesystem management"
    )}

    <section class="grid grid-2">

      <div class="card">

        <div class="card-header">

          <div>
            <div class="card-title">
              Filesystems
            </div>

            <div class="card-subtitle">
              Mounted filesystems
            </div>
          </div>

          <button
            class="btn"
            onclick="toast('Filesystem scan completed')">
            Scan
          </button>

        </div>

        ${[
          ["/dev/sda1","/","500 GB","354 GB","71%","bar-blue"],
          ["docker-vol","/var/lib/docker","220 GB","198 GB","90%","bar-red"],
          ["data","/home","1 TB","440 GB","44%","bar-purple"],
          ["backup","/mnt/backup","2 TB","820 GB","41%","bar-green"]
        ].map(x=>`

          <div class="storage-item">

            <div class="storage-head">

              <span>
                <strong>${x[1]}</strong>
                <span style="margin-left:7px;color:var(--muted2)">
                  ${x[0]}
                </span>
              </span>

              <span>${x[4]}</span>

            </div>

            <div class="progress">

              <div
                class="progress-bar ${x[5]}"
                style="width:${x[4]}"
              ></div>

            </div>

            <div style="
              margin-top:5px;
              color:var(--muted);
              font-size:9px;
            ">
              ${x[3]} used of ${x[2]}
            </div>

          </div>

        `).join("")}

      </div>


      <div class="card">

        <div class="card-header">

          <div>
            <div class="card-title">
              Disk I/O
            </div>

            <div class="card-subtitle">
              Current activity
            </div>
          </div>

        </div>

        <div class="info-grid">

          <div class="info-item">
            <div class="info-label">Read</div>
            <div class="info-value">42.8 MB/s</div>
          </div>

          <div class="info-item">
            <div class="info-label">Write</div>
            <div class="info-value">18.4 MB/s</div>
          </div>

          <div class="info-item">
            <div class="info-label">IOPS</div>
            <div class="info-value">1,284</div>
          </div>

          <div class="info-item">
            <div class="info-label">Inodes</div>
            <div class="info-value">42%</div>
          </div>

        </div>

        <div style="height:16px"></div>

        <div style="
          color:var(--muted);
          font-size:10px;
          line-height:1.8;
        ">
          Largest directories:
          <br>
          /var/lib/docker · 180 GB
          <br>
          /var/log · 23 GB
          <br>
          /home · 18 GB
        </div>

      </div>

    </section>

  `;
}


/* =========================================================
   NETWORK
========================================================= */

function renderNetwork(){

  app.innerHTML = `

    ${updateTopbar(
      "Network",
      "Network interfaces and connections"
    )}

    <section class="grid grid-3">

      <div class="stat-card">
        <div class="stat-top">
          <span>Download</span>
          <div class="stat-icon">↓</div>
        </div>
        <div class="stat-value">12.4</div>
        <div class="stat-bottom">
          <span>MB/s</span>
          <span class="positive">Normal</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-top">
          <span>Upload</span>
          <div class="stat-icon">↑</div>
        </div>
        <div class="stat-value">4.8</div>
        <div class="stat-bottom">
          <span>MB/s</span>
          <span class="positive">Normal</span>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-top">
          <span>Connections</span>
          <div class="stat-icon">⇄</div>
        </div>
        <div class="stat-value">148</div>
        <div class="stat-bottom">
          <span>TCP / UDP</span>
          <span class="positive">Stable</span>
        </div>
      </div>

    </section>

    <div style="height:16px"></div>

    <div class="card">

      <div class="card-header">

        <div>
          <div class="card-title">
            Network Interfaces
          </div>

          <div class="card-subtitle">
            Interface configuration
          </div>
        </div>

      </div>

      <div class="table-wrap">

        <table>

          <thead>
            <tr>
              <th>Interface</th>
              <th>Status</th>
              <th>IP Address</th>
              <th>MAC</th>
              <th>RX</th>
              <th>TX</th>
            </tr>
          </thead>

          <tbody>

            <tr>
              <td><strong>eth0</strong></td>
              <td>${statusBadge("running")}</td>
              <td>192.168.1.20</td>
              <td>52:54:00:3a:92:11</td>
              <td>12.4 MB/s</td>
              <td>4.8 MB/s</td>
            </tr>

            <tr>
              <td><strong>docker0</strong></td>
              <td>${statusBadge("running")}</td>
              <td>172.17.0.1</td>
              <td>02:42:9c:18:7a:44</td>
              <td>2.1 MB/s</td>
              <td>1.7 MB/s</td>
            </tr>

          </tbody>

        </table>

      </div>

    </div>

    <div style="height:16px"></div>

    <div class="card">

      <div class="card-header">

        <div>
          <div class="card-title">
            Listening Ports
          </div>

          <div class="card-subtitle">
            Services accepting connections
          </div>
        </div>

      </div>

      <div class="table-wrap">

        <table>

          <thead>
            <tr>
              <th>Port</th>
              <th>Protocol</th>
              <th>Process</th>
              <th>Address</th>
            </tr>
          </thead>

          <tbody>

            <tr>
              <td>22</td>
              <td>TCP</td>
              <td>sshd</td>
              <td>0.0.0.0</td>
            </tr>

            <tr>
              <td>80</td>
              <td>TCP</td>
              <td>nginx</td>
              <td>0.0.0.0</td>
            </tr>

            <tr>
              <td>443</td>
              <td>TCP</td>
              <td>nginx</td>
              <td>0.0.0.0</td>
            </tr>

            <tr>
              <td>5432</td>
              <td>TCP</td>
              <td>postgres</td>
              <td>127.0.0.1</td>
            </tr>

          </tbody>

        </table>

      </div>

    </div>

  `;
}


/* =========================================================
   DOCKER
========================================================= */

function renderDocker(){

  app.innerHTML = `

    ${updateTopbar(
      "Docker",
      "Container management"
    )}

    <div class="card">

      <div class="toolbar">

        <input
          class="search"
          id="dockerSearch"
          placeholder="Search container..."
          oninput="filterTable('dockerSearch','dockerTable')"
        />

        <button
          class="btn primary"
          onclick="toast('Pull container images started')">
          + Deploy
        </button>

      </div>

      <div class="table-wrap">

        <table id="dockerTable">

          <thead>
            <tr>
              <th>Container</th>
              <th>Image</th>
              <th>Status</th>
              <th>CPU</th>
              <th>Memory</th>
              <th>Ports</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>

            ${state.containers.map((c,i)=>`

              <tr>

                <td><strong>${escapeHtml(c.name)}</strong></td>

                <td>${escapeHtml(c.image)}</td>

                <td>${statusBadge(c.status)}</td>

                <td>${c.cpu}</td>

                <td>${c.memory}</td>

                <td>${c.ports}</td>

                <td>

                  <div class="row-actions">

                    <button
                      class="action-btn"
                      onclick="dockerAction(${i},'restart')">
                      Restart
                    </button>

                    <button
                      class="action-btn"
                      onclick="dockerAction(${i},'stop')">
                      Stop
                    </button>

                    <button
                      class="action-btn"
                      onclick="toast('Opening logs for ${escapeHtml(c.name)}')">
                      Logs
                    </button>

                  </div>

                </td>

              </tr>

            `).join("")}

          </tbody>

        </table>

      </div>

    </div>

  `;
}


function dockerAction(index,action){

  const container =
    state.containers[index];

  if(action === "restart"){
    container.status = "running";
    toast(`${container.name} restarted`);
  }

  if(action === "stop"){
    container.status = "stopped";
    toast(`${container.name} stopped`);
  }

  renderDocker();
}


/* =========================================================
   FIREWALL
========================================================= */

function renderFirewall(){

  app.innerHTML = `

    ${updateTopbar(
      "Firewall",
      "UFW firewall management"
    )}

    <section class="grid grid-3">

      <div class="stat-card">

        <div class="stat-top">
          <span>Firewall</span>
          <div class="stat-icon">◈</div>
        </div>

        <div class="stat-value" style="color:var(--green)">
          ON
        </div>

        <div class="stat-bottom">
          <span>UFW enabled</span>
          <span class="positive">Protected</span>
        </div>

      </div>

      <div class="stat-card">

        <div class="stat-top">
          <span>Allowed Rules</span>
          <div class="stat-icon">✓</div>
        </div>

        <div class="stat-value">
          3
        </div>

        <div class="stat-bottom">
          <span>Inbound</span>
        </div>

      </div>

      <div class="stat-card">

        <div class="stat-top">
          <span>Blocked Rules</span>
          <div class="stat-icon">✕</div>
        </div>

        <div class="stat-value">
          3
        </div>

        <div class="stat-bottom">
          <span>Inbound</span>
        </div>

      </div>

    </section>

    <div style="height:16px"></div>

    <div class="card">

      <div class="card-header">

        <div>
          <div class="card-title">
            Firewall Rules
          </div>

          <div class="card-subtitle">
            UFW inbound rules
          </div>
        </div>

        <button
          class="btn primary"
          onclick="toast('Add rule dialog opened')">
          + Add Rule
        </button>

      </div>

      <div class="table-wrap">

        <table>

          <thead>
            <tr>
              <th>Port</th>
              <th>Protocol</th>
              <th>Service</th>
              <th>Action</th>
              <th>Source</th>
            </tr>
          </thead>

          <tbody>

            ${state.firewall.map(r=>`

              <tr>

                <td><strong>${r[0]}</strong></td>
                <td>${r[1]}</td>
                <td>${r[2]}</td>
                <td>${statusBadge(r[3].toLowerCase())}</td>
                <td>${r[4]}</td>

              </tr>

            `).join("")}

          </tbody>

        </table>

      </div>

    </div>

  `;
}


/* =========================================================
   USERS
========================================================= */

function renderUsers(){

  app.innerHTML = `

    ${updateTopbar(
      "Users",
      "Local users and accounts"
    )}

    <div class="card">

      <div class="toolbar">

        <input
          class="search"
          id="userSearch"
          placeholder="Search user..."
          oninput="filterTable('userSearch','userTable')"
        />

        <button
          class="btn primary"
          onclick="addUser()">
          + Create User
        </button>

      </div>

      <div class="table-wrap">

        <table id="userTable">

          <thead>
            <tr>
              <th>User</th>
              <th>UID</th>
              <th>Group</th>
              <th>Home</th>
              <th>Shell</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>

          <tbody>

            ${state.users.map((u,i)=>`

              <tr>

                <td><strong>${u[0]}</strong></td>
                <td>${u[1]}</td>
                <td>${u[2]}</td>
                <td>${u[3]}</td>
                <td>${u[4]}</td>
                <td>${statusBadge("active")}</td>

                <td>

                  <button
                    class="action-btn"
                    onclick="toast('User management for ${escapeHtml(u[0])}')">
                    Manage
                  </button>

                </td>

              </tr>

            `).join("")}

          </tbody>

        </table>

      </div>

    </div>

  `;
}


function addUser(){

  const username =
    prompt("Username baru:");

  if(!username){
    return;
  }

  state.users.push([
    username,
    String(1000 + state.users.length),
    username,
    `/home/${username}`,
    "/bin/bash",
    "Active"
  ]);

  toast(`User ${username} created`);

  renderUsers();
}


/* =========================================================
   TERMINAL
========================================================= */

function renderTerminal(){

  app.innerHTML = `

    ${updateTopbar(
      "Web Terminal",
      "Connected to ubuntu-prod-01"
    )}

    <div class="terminal">

      <div class="terminal-head">

        <div class="term-dot term-red"></div>
        <div class="term-dot term-yellow"></div>
        <div class="term-dot term-green"></div>

      </div>

      <div
        class="terminal-body"
        id="terminalBody">

        <div>
          Ubuntu Server Manager Terminal
        </div>

        <div class="term-output">
          Connected to ubuntu-prod-01
        </div>

        <br>

        <div class="term-output">
          Type "help" for available commands.
        </div>

        <br>

        <div class="term-input-row">

          <span class="term-prompt">
            root@ubuntu-prod-01:~$
          </span>

          <input
            class="term-input"
            id="terminalInput"
            autofocus
            autocomplete="off"
            onkeydown="terminalKey(event)"
          >

        </div>

      </div>

    </div>

  `;
}


function terminalKey(event){

  if(event.key !== "Enter"){
    return;
  }

  const input =
    document.getElementById("terminalInput");

  const command =
    input.value.trim();

  if(!command){
    return;
  }

  const body =
    document.getElementById("terminalBody");

  const output =
    document.createElement("div");

  output.innerHTML =
    `
      <div>
        <span class="term-prompt">
          root@ubuntu-prod-01:~$
        </span>
        ${escapeHtml(command)}
      </div>
      <div class="term-output">
        ${terminalCommand(command)}
      </div>
      <br>
    `;

  body.insertBefore(
    output,
    document.querySelector(".term-input-row")
  );

  input.value = "";

  body.scrollTop =
    body.scrollHeight;
}


function terminalCommand(command){

  const cmd =
    command.toLowerCase();

  if(cmd === "help"){

    return `
      Available:
      <br>
      systemctl status
      <br>
      docker ps
      <br>
      df -h
      <br>
      free -h
      <br>
      uptime
      <br>
      clear
    `;

  }

  if(cmd === "uptime"){
    return "14 days, 8 hours, 21 minutes";
  }

  if(cmd === "free -h"){
    return `
      Mem: 15.4Gi total / 10.1Gi used / 5.3Gi free
    `;
  }

  if(cmd === "df -h"){
    return `
      /dev/sda1  500G  354G  146G  71%  /
    `;
  }

  if(cmd === "docker ps"){
    return `
      nginx · postgres · redis · api
    `;
  }

  if(cmd === "systemctl status"){
    return `
      nginx active
      <br>
      postgresql active
      <br>
      docker active
      <br>
      redis active
      <br>
      ssh active
    `;
  }

  if(cmd === "clear"){
    document.getElementById(
      "terminalBody"
    ).innerHTML = `
      <div class="term-input-row">
        <span class="term-prompt">
          root@ubuntu-prod-01:~$
        </span>

        <input
          class="term-input"
          id="terminalInput"
          autofocus
          autocomplete="off"
          onkeydown="terminalKey(event)"
        >
      </div>
    `;

    document.getElementById(
      "terminalInput"
    ).focus();

    return "";
  }

  return `
    Command executed in prototype mode.
    <br>
    Real execution will be handled by the Ubuntu Agent.
  `;
}


/* =========================================================
   FILTER
========================================================= */

function filterTable(
  searchId,
  tableId
){

  const input =
    document.getElementById(searchId);

  const table =
    document.getElementById(tableId);

  const q =
    input.value.toLowerCase();

  [...table.tBodies[0].rows]
    .forEach(row=>{

      row.style.display =
        row.textContent
          .toLowerCase()
          .includes(q)
          ? ""
          : "none";

    });

}


/* =========================================================
   NAVIGATION
========================================================= */

function navigate(page){

  state.page = page;

  document
    .querySelectorAll(".nav-item")
    .forEach(item=>{
      item.classList.toggle(
        "active",
        item.dataset.page === page
      );
    });

  switch(page){

    case "dashboard":
      renderDashboard();
      break;

    case "services":
      renderServices();
      break;

    case "processes":
      renderProcesses();
      break;

    case "logs":
      renderLogs();
      break;

    case "storage":
      renderStorage();
      break;

    case "network":
      renderNetwork();
      break;

    case "docker":
      renderDocker();
      break;

    case "firewall":
      renderFirewall();
      break;

    case "users":
      renderUsers();
      break;

    case "terminal":
      renderTerminal();
      break;

    default:
      renderDashboard();

  }

}


/* =========================================================
   REFRESH
========================================================= */

function refreshPage(){

  toast("Refreshing server data...");

  setTimeout(()=>{

    switch(state.page){

      case "dashboard":
        renderDashboard();
        break;

      case "services":
        renderServices();
        break;

      case "processes":
        renderProcesses();
        break;

      case "logs":
        renderLogs();
        break;

      case "storage":
        renderStorage();
        break;

      case "network":
        renderNetwork();
        break;

      case "docker":
        renderDocker();
        break;

      case "firewall":
        renderFirewall();
        break;

      case "users":
        renderUsers();
        break;

      case "terminal":
        renderTerminal();
        break;

    }

  },400);

}


/* =========================================================
   NAV LISTENERS
========================================================= */

document
  .querySelectorAll(".nav-item")
  .forEach(item=>{

    item.addEventListener(
      "click",
      ()=>navigate(item.dataset.page)
    );

  });


/* =========================================================
   SERVER SWITCHER
========================================================= */

document
  .getElementById("serverSelect")
  .addEventListener(
    "change",
    function(){

      toast(
        `Switched to ${this.value}`
      );

    }
  );


/* =========================================================
   REALTIME SIMULATION
========================================================= */

setInterval(()=>{

  state.cpu =
    Math.max(
      10,
      Math.min(
        80,
        state.cpu +
        Math.floor(Math.random()*9)-4
      )
    );

  state.ram =
    Math.max(
      40,
      Math.min(
        85,
        state.ram +
        Math.floor(Math.random()*5)-2
      )
    );

  state.load =
    Math.max(
      .2,
      state.load +
      (Math.random()*.3-.15)
    );

  if(
    state.page === "dashboard"
  ){

    const cpu =
      document.getElementById("cpuValue");

    const ram =
      document.getElementById("ramValue");

    const load =
      document.getElementById("loadValue");

    if(cpu)
      cpu.textContent =
        state.cpu + "%";

    if(ram)
      ram.textContent =
        state.ram + "%";

    if(load)
      load.textContent =
        state.load.toFixed(2);

  }

},3000);


/* =========================================================
   INITIAL PAGE
========================================================= */

renderDashboard();

</script>

</body>
</html>
```

### Struktur halaman yang sekarang

```text
Dashboard
│
├── Server Overview
│   ├── Health
│   ├── CPU
│   ├── RAM
│   ├── Storage
│   ├── Load Average
│   ├── Performance
│   ├── Services
│   ├── Network
│   └── Activity
│
├── Services
│   ├── Service list
│   ├── Start
│   ├── Stop
│   └── Restart
│
├── Processes
│   ├── PID
│   ├── CPU
│   ├── RAM
│   └── Kill
│
├── Logs
│   ├── Search
│   ├── INFO
│   ├── WARN
│   └── ERROR
│
├── Storage
│   ├── Filesystem
│   ├── Disk usage
│   └── Disk I/O
│
├── Network
│   ├── Interface
│   ├── Traffic
│   ├── Connections
│   └── Listening ports
│
├── Docker
│   ├── Containers
│   ├── CPU
│   ├── RAM
│   ├── Restart
│   ├── Stop
│   └── Logs
│
├── Firewall
│   ├── UFW status
│   ├── Rules
│   └── Add rule
│
├── Users
│   ├── User list
│   └── Create user
│
└── Terminal
    └── Web terminal prototype
```

Yang berubah cukup signifikan dibanding versi pertama: **sidebar sekarang benar-benar menjadi navigasi aplikasi**, bukan sekadar visual. Semua page dirender secara client-side sehingga nanti tinggal kita sambungkan ke endpoint FastAPI.

Untuk tahap berikutnya, pola yang paling pas adalah mengganti data simulasi seperti `state.cpu`, `state.services`, `state.processes`, dan `state.containers` menjadi API nyata:

```text
Next.js / HTML UI
        ↓
FastAPI
        ↓
WebSocket / REST
        ↓
Go Ubuntu Agent
        ↓
systemd / Docker / UFW / Linux
```

Dengan begitu prototype ini bisa berkembang langsung menjadi **server management panel yang benar-benar mengontrol Ubuntu**, tanpa perlu merombak desain UI-nya.
