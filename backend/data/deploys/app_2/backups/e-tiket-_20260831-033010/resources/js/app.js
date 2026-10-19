// ===== E-Tiket Report: Shared UI JavaScript =====

// Tanggal (header, format Indonesia)
function initCurrentDate() {
    const el = document.getElementById('currentDate');
    if (!el) return;

    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    el.textContent = new Date().toLocaleDateString('id-ID', options);
}

// Sidebar toggle (mobile)
function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobileOverlay');
    if (!sidebar || !overlay) return;

    window.toggleSidebar = () => {
        sidebar.classList.toggle('-translate-x-full');
        overlay.classList.toggle('hidden');
    };
}

// Toast notification
let toastTimeout;

window.showToast = function showToast(message, isError = false) {
    const toast = document.getElementById('toast');
    if (!toast) return;

    const successIcon = document.getElementById('toastIconSuccess');
    const errorIcon = document.getElementById('toastIconError');

    document.getElementById('toastMessage').textContent = message;
    if (successIcon && errorIcon) {
        successIcon.classList.toggle('hidden', isError);
        errorIcon.classList.toggle('hidden', !isError);
    }

    toast.classList.remove('translate-y-20', 'opacity-0');
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => {
        toast.classList.add('translate-y-20', 'opacity-0');
    }, 3500);
};

initCurrentDate();
initSidebar();
