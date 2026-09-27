// AssureX Claim Engine - Minimal Client Interactivity
document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts after 5 seconds if marked auto-dismiss
    const autoAlerts = document.querySelectorAll('.alert-dismissible');
    autoAlerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 200);
        }, 5000);
    });

    // Client-side quick table search filter
    const searchInputs = document.querySelectorAll('[data-table-search]');
    searchInputs.forEach(function(input) {
        const tableId = input.getAttribute('data-table-search');
        const targetTable = document.getElementById(tableId);
        if (!targetTable) return;

        input.addEventListener('keyup', function() {
            const query = this.value.toLowerCase();
            const rows = targetTable.querySelectorAll('tbody tr');
            rows.forEach(function(row) {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(query) ? '' : 'none';
            });
        });
    });
});
