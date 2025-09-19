// calendar.js - Main Calendar Class
class Calendar {
  constructor() {
    this.currentDate = new Date();
    this.events = [];
    this.layers = [];
    this.recurringPatterns = [];
    this.currentView = 'month';
    this.selectedDate = null;
    this.currentEditingEvent = null;
    this.currentEditType = null;
    this.layerToDelete = null;
    this.dayZoom = 0.6;
    this.kanbanZoom = 1;
    
    // Initialize modules
    this.dragDrop = new DragDropHandler(this);
    this.dayModal = new DayModalManager(this);
    this.taskManager = new TaskManager(this);
    this.layerManager = new LayerManager(this);
    this.eventManager = new EventManager(this);
    this.renderer = new CalendarRenderer(this);
    
    this.init();
  }

  async init() {
    await this.loadLayers();
    await this.loadEvents();
    this.bindEvents();
    this.render();
  }

  // API Methods
  async loadLayers() {
    try {
      const response = await fetch('/api/layers');
      this.layers = await response.json();
      this.layerManager.renderLayersControls();
      this.layerManager.populateLayerSelect();
    } catch (error) {
      console.error('Error loading layers:', error);
    }
  }

  async loadEvents() {
    try {
      const response = await fetch('/api/events');
      this.events = await response.json();
      this.render();
    } catch (error) {
      console.error('Error loading events:', error);
    }
  }

  async loadRecurringPatterns() {
    try {
      const response = await fetch('/api/recurring-patterns');
      this.recurringPatterns = await response.json();
    } catch (error) {
      console.error('Error loading recurring patterns:', error);
    }
  }

  // Navigation Methods
  navigateDate(direction) {
    switch(this.currentView) {
      case 'month':
        this.currentDate.setMonth(this.currentDate.getMonth() + direction);
        break;
      case 'week':
        this.currentDate.setDate(this.currentDate.getDate() + (direction * 7));
        break;
      case 'day':
        this.currentDate.setDate(this.currentDate.getDate() + direction);
        break;
      case 'recurring':
        return; // No navigation for recurring view
    }
    this.render();
  }

  switchView(view) {
    this.currentView = view;
    this.render();
  }

  // Render Methods
  render() {
    this.renderer.updateDateDisplay();
    this.renderer.updateViewButtons();
    this.renderer.renderCurrentView();
  }

  // Event binding
  bindEvents() {
    // Navigation
    document.getElementById('prevMonth').addEventListener('click', () => {
      this.navigateDate(-1);
    });
    
    document.getElementById('nextMonth').addEventListener('click', () => {
      this.navigateDate(1);
    });
    
    document.getElementById('todayBtn').addEventListener('click', () => {
      this.currentDate = new Date();
      this.render();
    });

    // View switching
    document.getElementById('monthView').addEventListener('click', () => {
      this.switchView('month');
    });
    
    document.getElementById('weekView').addEventListener('click', () => {
      this.switchView('week');
    });
    
    document.getElementById('dayView').addEventListener('click', () => {
      this.switchView('day');
    });
    
    document.getElementById('recurringView').addEventListener('click', () => {
      this.switchView('recurring');
    });

    // Layer controls
    document.getElementById('hideAllLayers').addEventListener('click', () => {
      this.layerManager.toggleAllLayers(false);
    });
    
    document.getElementById('showAllLayers').addEventListener('click', () => {
      this.layerManager.toggleAllLayers(true);
    });

    // Event form handlers
    this.eventManager.bindEventHandlers();
    this.layerManager.bindLayerHandlers();
  }

  // Utility Methods
  getEventsForDay(date) {
    const dateStr = this.toLocalYMD(date);
    return this.events.filter(event => {
      const eventStart = new Date(event.start);
      const eventDateStr = this.toLocalYMD(eventStart);
      return eventDateStr === dateStr;
    });
  }

  getEventsForHour(date, hour) {
    const dateStr = this.toLocalYMD(date);
    return this.events.filter(event => {
      const eventStart = new Date(event.start);
      const eventDateStr = this.toLocalYMD(eventStart);
      return eventDateStr === dateStr && eventStart.getHours() === hour;
    });
  }

  toLocalYMD(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  formatHHMM(d) {
    return new Date(d).toLocaleTimeString([], { 
      hour: 'numeric', 
      minute: '2-digit' 
    });
  }

  getWeekStart(date) {
    const d = new Date(date);
    const day = d.getDay();
    const diff = d.getDate() - day;
    return new Date(d.setDate(diff));
  }

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}