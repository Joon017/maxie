// calendar-init.js - Calendar Initialization
let calendar;

document.addEventListener('DOMContentLoaded', () => {
  calendar = new Calendar();
});

// Extension methods for Calendar class
Calendar.prototype.setDayZoom = function(delta) {
  this.dayModal.setDayZoom(delta);
};

Calendar.prototype.openDayModal = function(date) {
  this.dayModal.openDayModal(date);
};

// Global helper functions for compatibility
function ensureDayModalShell() {
  if (calendar && calendar.dayModal) {
    calendar.dayModal.ensureDayModalShell();
  }
}

// Expose calendar instance globally for HTML onclick handlers
window.calendar = calendar;