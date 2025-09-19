
// --- constants used by the modal day view ---
const PX_PER_MIN = 1.0;      // 60px per hour (change to taste)
const DAY_MINUTES = 24 * 60;

function ensureDayModalShell() {
  if (document.getElementById('dayModal')) return;

  document.body.insertAdjacentHTML('beforeend', `
  <div class="modal fade" id="dayModal" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog modal-xl modal-dialog-scrollable">
      <div class="modal-content">
        <div class="modal-header">
          <div class="d-flex align-items-center gap-2">
            <button class="btn btn-sm btn-outline-secondary" id="dayModalPrev" title="Previous day">‹</button>
            <h5 class="modal-title day-modal-title mb-0"></h5>
            <button class="btn btn-sm btn-outline-secondary" id="dayModalNext" title="Next day">›</button>
          </div>
          <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>

        <div class="modal-body day-modal-body p-0" style="height:70vh; overflow:auto;">
          <div class="d-flex" style="position:relative;">
            <div class="day-modal-ruler" style="width:110px; border-right:1px solid var(--border-color);"></div>
            <div class="day-modal-grid position-relative flex-grow-1"></div>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-primary" id="dayModalNewEvent">+ New Event</button>
          <button class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
        </div>
      </div>
    </div>
  </div>
  `);
}

class Calendar {
    constructor() {
        this.currentDate = new Date();
        this.events = [];
        this.layers = [];
        this.recurringPatterns = [];
        this.currentView = 'month';
        this.selectedDate = null;
        this.draggedEvent = null;
        this.dropTarget = null;
        this.currentEditingEvent = null;
        this.currentEditType = null;
        this.layerToDelete = null;
        
        this.init();
    }

    dayZoom = 0.6; // default: 0.6px per minute (~36px per hour)

    init() {
        this.loadLayers();
        this.loadEvents();
        this.bindEvents();
        this.render();
    }

    // Call this once after the DOM is ready (e.g., in constructor or init())
initKanbanWiring() {
  const kbModalEl = document.getElementById('kanbanModal');
  if (!kbModalEl) return;

  // Zoom buttons (optional, keep if you already use them)
  const zoomOut = document.getElementById('kanbanZoomOut');
  const zoomIn  = document.getElementById('kanbanZoomIn');
  const zoomLbl = document.getElementById('kanbanZoomLabel');
  this.kanbanZoom = this.kanbanZoom ?? 1; // 1 = 100%

  const applyZoom = () => {
    zoomLbl.textContent = `${Math.round(this.kanbanZoom * 100)}%`;
    kbModalEl.querySelector('.kb-board').style.zoom = this.kanbanZoom;
  };
  zoomOut?.addEventListener('click', () => { this.kanbanZoom = Math.max(0.7, this.kanbanZoom - 0.1); applyZoom(); });
  zoomIn?.addEventListener('click',  () => { this.kanbanZoom = Math.min(1.5, this.kanbanZoom + 0.1); applyZoom(); });

  // New Task button
  const kbNewTaskBtn = document.getElementById('kbNewTaskBtn');
  kbNewTaskBtn?.addEventListener('click', () => {
    const ymd = kbModalEl.dataset.ymd || this.toLocalYMD(new Date());
    this.openTaskModal({ ymd }); // opens the editor empty
  });

  // Keep a handle to the bootstrap modal
  this._kanbanModal = this._kanbanModal || new bootstrap.Modal(kbModalEl);
}

// Put this inside your Calendar class
escapeHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Example cardHTML that uses escapeHtml
cardHTML(t) {
  return `
    <div class="kb-card" draggable="true" data-id="${t.id}">
      <div class="kb-card-title">${this.escapeHtml(t.title)}</div>
      <div class="kb-card-meta">
        ${t.due_at ? `Due: ${new Date(t.due_at).toLocaleString()}` : ''}
      </div>
      <div class="kb-card-details">
        ${this.escapeHtml(t.details || '')}
      </div>
      <div class="kb-card-actions mt-1">
        <button class="btn btn-sm btn-outline-secondary kb-edit" data-id="${t.id}">Edit</button>
        <button class="btn btn-sm btn-outline-danger kb-del" data-id="${t.id}">Delete</button>
      </div>
    </div>
  `;
}
    

        // ---- tasks/notes local storage helpers ----
    _storageKeyTasks(ymd) { return `tasks:${ymd}`; }
    _storageKeyNotes(ymd) { return `notes:${ymd}`; }

    _loadTasks(ymd) {
    try { return JSON.parse(localStorage.getItem(this._storageKeyTasks(ymd))) || []; }
    catch { return []; }
    }
    _saveTasks(ymd, arr) {
    localStorage.setItem(this._storageKeyTasks(ymd), JSON.stringify(arr));
    }

    _loadNotes(ymd) {
    return localStorage.getItem(this._storageKeyNotes(ymd)) || '';
    }
    _saveNotes(ymd, text) {
    localStorage.setItem(this._storageKeyNotes(ymd), text);
    }

    // tiny debounce for notes typing
    _debounce(fn, ms=300) {
    let t; return (...args) => { clearTimeout(t); t=setTimeout(()=>fn.apply(this,args),ms); };
    }


    async loadLayers() {
        try {
            const response = await fetch('/api/layers');
            this.layers = await response.json();
            this.renderLayersControls();
            this.populateLayerSelect();
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

    setDayZoom(delta) {
        // Clamp zoom between 0.4 (24px/hour) and 1.2 (72px/hour)
        this.dayZoom = Math.min(1.2, Math.max(0.4, this.dayZoom + delta));
        this.renderDayModal();
        }
    
        // 12:30 → "12:30", 9:00 → "9:00"
    formatHHMM(d) {
    return new Date(d).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }

    // What the month cell shows for an event
    getMonthCellLabel(ev) {
    // All-day: just title
    if (ev.all_day) return ev.title;

    // Timed: 09:00 Title
    const t = this.formatHHMM(ev.start);
    return `${t} ${ev.title}`;
    }

    // Decide how many events to show per cell.
    // It’s robust and responsive without measuring DOM each time.
    getMaxEventsPerCell() {
  const calendarView = document.getElementById('calendarView');
  const row = calendarView.querySelector('.calendar-day'); 
  if (!row) return 3; // fallback
  
  // Estimate how many "event rows" fit in the cell
  const cellHeight = row.offsetHeight;   // actual rendered height
  const approxEventHeight = 22;          // px per event pill + gap
  const maxByHeight = Math.floor((cellHeight - 20) / approxEventHeight); // subtract top date label
  
  // Add width rules as safeguard
  const w = window.innerWidth;
  let maxByWidth = 3;
  if (w < 576) maxByWidth = 2;
  if (w >= 992) maxByWidth = 4;

  return Math.min(maxByHeight, maxByWidth);
}


    bindEvents() {
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

        document.getElementById('hideAllLayers').addEventListener('click', () => {
            this.toggleAllLayers(false);
        });

        document.getElementById('showAllLayers').addEventListener('click', () => {
            this.toggleAllLayers(true);
        });

        document.getElementById('saveEvent').addEventListener('click', () => {
            this.saveEvent();
        });

        document.getElementById('deleteEvent').addEventListener('click', () => {
            this.deleteEvent();
        });

        document.getElementById('copyEvent').addEventListener('click', () => {
            this.copyEvent();
        });

        document.getElementById('confirmMove').addEventListener('click', () => {
            this.confirmMoveEvent();
        });

        document.getElementById('allDay').addEventListener('change', (e) => {
            const startInput = document.getElementById('eventStart');
            const endInput = document.getElementById('eventEnd');
            
            if (e.target.checked) {
                startInput.type = 'date';
                endInput.type = 'date';
            } else {
                startInput.type = 'datetime-local';
                endInput.type = 'datetime-local';
            }
        });

        document.getElementById('isRecurring').addEventListener('change', (e) => {
            const recurringOptions = document.getElementById('recurringOptions');
            if (e.target.checked) {
                recurringOptions.style.display = 'block';
            } else {
                recurringOptions.style.display = 'none';
            }
        });

        document.getElementById('recurrenceType').addEventListener('change', (e) => {
            const intervalUnit = document.getElementById('intervalUnit');
            const value = e.target.value;
            if (value === 'daily') {
                intervalUnit.textContent = 'day(s)';
            } else if (value === 'weekly') {
                intervalUnit.textContent = 'week(s)';
            } else if (value === 'monthly') {
                intervalUnit.textContent = 'month(s)';
            }
        });

        // Reset modal when it's closed
        document.getElementById('eventModal').addEventListener('hidden.bs.modal', () => {
            this.resetModal();
        });

        document.getElementById('moveConfirmModal').addEventListener('hidden.bs.modal', () => {
            this.resetDragState();
        });

        document.getElementById('confirmDeleteLayer').addEventListener('click', () => {
            this.confirmDeleteLayer();
        });

        document.getElementById('saveLayer').addEventListener('click', () => {
            this.saveLayer();
        });

        // Color picker selection
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('color-option')) {
                // Remove selected class from all options
                document.querySelectorAll('.color-option').forEach(opt => opt.classList.remove('selected'));
                // Add selected class to clicked option
                e.target.classList.add('selected');
                // Set hidden input value
                document.getElementById('layerColor').value = e.target.dataset.color;
            }
        });

        // Reset modals when closed
        document.getElementById('layerModal').addEventListener('hidden.bs.modal', () => {
            this.resetLayerModal();
        });

        document.getElementById('deleteLayerModal').addEventListener('hidden.bs.modal', () => {
            this.resetDeleteLayerModal();
        });
    }

    render() {
        this.updateDateDisplay();
        this.updateViewButtons();
        
        switch(this.currentView) {
            case 'month':
                this.renderMonthView();
                break;
            case 'week':
                this.renderWeekView();
                break;
            case 'day':
                this.renderDayView();
                break;
            case 'recurring':
                this.renderRecurringView();
                break;
        }
    }

    // minutes since start of day in local time
    minutesIntoDay(d) {
    return d.getHours() * 60 + d.getMinutes();
    }

    // get all events that start on this day (local)
    getEventsForDate(date) {
    const dayStr = this.toLocalYMD(date);
    return this.events.filter(ev => this.toLocalYMD(new Date(ev.start)) === dayStr);
    }

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
                // No navigation for recurring view
                return;
        }
        this.render();
    }

    switchView(view) {
        this.currentView = view;
        this.render();
    }

    updateViewButtons() {
        document.querySelectorAll('.view-buttons .btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.getElementById(`${this.currentView}View`).classList.add('active');
    }

    updateDateDisplay() {
        const monthNames = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ];
        
        const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
        
        let displayText;
        switch(this.currentView) {
            case 'month':
                displayText = `${monthNames[this.currentDate.getMonth()]} ${this.currentDate.getFullYear()}`;
                break;
            case 'week':
                const weekStart = this.getWeekStart(this.currentDate);
                const weekEnd = new Date(weekStart);
                weekEnd.setDate(weekEnd.getDate() + 6);
                
                if (weekStart.getMonth() === weekEnd.getMonth()) {
                    displayText = `${monthNames[weekStart.getMonth()]} ${weekStart.getDate()} - ${weekEnd.getDate()}, ${weekStart.getFullYear()}`;
                } else {
                    displayText = `${monthNames[weekStart.getMonth()]} ${weekStart.getDate()} - ${monthNames[weekEnd.getMonth()]} ${weekEnd.getDate()}, ${weekStart.getFullYear()}`;
                }
                break;
            case 'day':
                displayText = `${dayNames[this.currentDate.getDay()]}, ${monthNames[this.currentDate.getMonth()]} ${this.currentDate.getDate()}, ${this.currentDate.getFullYear()}`;
                break;
            case 'recurring':
                displayText = 'Recurring Events';
                break;
        }
        
        document.getElementById('currentMonth').textContent = displayText;
    }

    getWeekStart(date) {
        const d = new Date(date);
        const day = d.getDay();
        const diff = d.getDate() - day;
        return new Date(d.setDate(diff));
    }

   renderMonthView() {
  const calendarView = document.getElementById('calendarView');
  const firstDay = new Date(this.currentDate.getFullYear(), this.currentDate.getMonth(), 1);
  const startDate = new Date(firstDay);
  startDate.setDate(startDate.getDate() - firstDay.getDay());

  let html = `
    <div class="calendar-grid">
      <div class="row calendar-header-row g-0">
        <div class="col calendar-header-cell">Sun</div>
        <div class="col calendar-header-cell">Mon</div>
        <div class="col calendar-header-cell">Tue</div>
        <div class="col calendar-header-cell">Wed</div>
        <div class="col calendar-header-cell">Thu</div>
        <div class="col calendar-header-cell">Fri</div>
        <div class="col calendar-header-cell">Sat</div>
      </div>
  `;

  const today = new Date();

  for (let week = 0; week < 6; week++) {
    html += '<div class="row g-0">';

    for (let day = 0; day < 7; day++) {
      const cellDate = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
      const isCurrentMonth = cellDate.getMonth() === this.currentDate.getMonth();
      const isToday = cellDate.toDateString() === today.toDateString();
      const dayEvents = this.getEventsForDay(cellDate);

      let dayClass = 'calendar-day';
      if (!isCurrentMonth) dayClass += ' other-month';
      if (isToday) dayClass += ' today';

      const dateString = [
        cellDate.getFullYear(),
        String(cellDate.getMonth() + 1).padStart(2, '0'),
        String(cellDate.getDate()).padStart(2, '0')
      ].join('-');

      const sorted = [...dayEvents].sort((a, b) => new Date(a.start) - new Date(b.start));
      const MAX = this.getMaxEventsPerCell();               // helper below
      const visible = sorted.slice(0, MAX);
      const hiddenCount = Math.max(0, sorted.length - visible.length);

      html += `
        <div class="col ${dayClass} drop-zone" data-date="${dateString}" title="Date: ${dateString}">
          <div class="day-number">${cellDate.getDate()}</div>
          ${visible.map(ev => {
            const showRecurringBadge = !!ev.is_recurring_linked;
            const showMovedDot      = !!ev.is_moved_exception;
            const isAllDay          = !!ev.all_day;
            const timeText          = isAllDay ? '' : this.formatHHMM(ev.start); // helper below
            const titleAttr         = isAllDay
              ? ev.title
              : `${this.formatHHMM(ev.start)}–${this.formatHHMM(ev.end)} · ${ev.title}`;

            return `
              <div class="event month-event-row ${showRecurringBadge ? 'recurring-event' : ''}"
                   draggable="true"
                   data-event-id="${ev.id}"
                   title="${titleAttr.replace(/"/g,'&quot;')}"
                   style="background-color:${ev.layer_color || '#28a745'}">
                ${showRecurringBadge ? '<span class="recurring-indicator" title="Part of series"></span>' : ''}
                ${showMovedDot ? '<span class="recurring-indicator moved" title="Moved from series"></span>' : ''}
                ${timeText ? `<span class="event-time">${timeText}</span>` : ''}
                <span class="event-title">${ev.title}</span>
              </div>
            `;
          }).join('')}
          ${hiddenCount > 0 ? `
            <button type="button" class="month-more btn btn-link p-0" data-date="${dateString}">
              +${hiddenCount} more
            </button>` : ''
          }
        </div>
      `;

      startDate.setDate(startDate.getDate() + 1);
    }

    html += '</div>';
  }

  html += '</div>';
  calendarView.innerHTML = html;

  // open day modal from “+N more”
  calendarView.querySelectorAll('.month-more').forEach(btn => {
    btn.addEventListener('click', e => this.openDayModal(e.currentTarget.dataset.date));
  });

  this.bindCalendarEvents();
}



    renderWeekView() {
    const calendarView = document.getElementById('calendarView');
    const weekStart = this.getWeekStart(this.currentDate);
    const today = new Date();

    let html = `
        <div class="calendar-grid">
            <div class="row calendar-header-row g-0">
                <div class="col-1 calendar-header-cell">Time</div>
    `;

    for (let i = 0; i < 7; i++) {
        const day = new Date(weekStart);
        day.setDate(day.getDate() + i);
        const isToday = day.toDateString() === today.toDateString();
        const dayName = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][i];

        html += `
            <div class="col calendar-header-cell ${isToday ? 'text-primary fw-bold' : ''}">
                ${dayName} ${day.getDate()}
            </div>
        `;
    }

    html += '</div>';

    for (let hour = 0; hour < 24; hour++) {
        html += '<div class="row g-0" style="min-height: 60px; border-bottom: 1px solid var(--border-color);">';

        const timeStr = hour === 0 ? '12 AM' : 
                       hour < 12 ? `${hour} AM` : 
                       hour === 12 ? '12 PM' : `${hour - 12} PM`;

        html += `<div class="col-1 p-2 text-end" style="font-size: 0.8rem; color: #666; border-right: 1px solid var(--border-color);">${timeStr}</div>`;

        for (let i = 0; i < 7; i++) {
            const day = new Date(weekStart);
            day.setDate(day.getDate() + i);
            const dayEvents = this.getEventsForHour(day, hour);
            const isToday = day.toDateString() === today.toDateString();

            html += `
                <div class="col week-day-cell drop-zone ${isToday ? 'today' : ''}" 
                     data-date="${this.toLocalYMD(day)}"
                     data-hour="${hour}"
                     style="border-right: 1px solid var(--border-color); cursor: pointer; position: relative;">
                    ${dayEvents.map(event => {
                        const showRecurringBadge = event.is_recurring_linked;
                        const showMovedDot = event.is_moved_exception;
                        return `
                            <div class="event ${showRecurringBadge ? 'recurring-event' : ''}" 
                                 draggable="true" data-event-id="${event.id}" 
                                 style="position: absolute; top: 2px; left: 2px; right: 2px; z-index: 2; background-color: ${event.layer_color || '#007bff'};">
                                ${showRecurringBadge ? '<span class="recurring-indicator" title="Part of recurring series"></span>' : ''}
                                ${showMovedDot ? '<span class="recurring-indicator moved" title="Moved from series"></span>' : ''}
                                ${event.title}
                            </div>
                        `;
                    }).join('')}
                </div>
            `;
        }

        html += '</div>';
    }

    html += '</div>';
    calendarView.innerHTML = html;
    this.bindCalendarEvents();
}


    renderDayView() {
    const calendarView = document.getElementById('calendarView');
    const today = new Date();
    const isToday = this.currentDate.toDateString() === today.toDateString();

    let html = `
        <div class="calendar-grid">
            <div class="row calendar-header-row g-0">
                <div class="col-2 calendar-header-cell">Time</div>
                <div class="col calendar-header-cell ${isToday ? 'text-primary fw-bold' : ''}">
                    ${this.currentDate.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
                </div>
            </div>
    `;

    for (let hour = 0; hour < 24; hour++) {
        const timeStr = hour === 0 ? '12:00 AM' : 
                       hour < 12 ? `${hour}:00 AM` : 
                       hour === 12 ? '12:00 PM' : `${hour - 12}:00 PM`;

        const dayEvents = this.getEventsForHour(this.currentDate, hour);

        html += `
            <div class="row g-0" style="min-height: 80px; border-bottom: 1px solid var(--border-color);">
                <div class="col-2 p-3 text-end" style="font-size: 0.9rem; color: #666; border-right: 1px solid var(--border-color);">
                    ${timeStr}
                </div>
                <div class="col day-hour-cell drop-zone ${isToday ? 'today' : ''}" 
                     data-date="${this.currentDate.toISOString().split('T')[0]}" 
                     data-hour="${hour}"
                     style="cursor: pointer; position: relative; padding: 0.5rem;">
                    ${dayEvents.map(event => {
                        const showRecurringBadge = event.is_recurring_linked;
                        const showMovedDot = event.is_moved_exception;
                        return `
                            <div class="event mb-1 ${showRecurringBadge ? 'recurring-event' : ''}" 
                                 draggable="true" data-event-id="${event.id}" 
                                 style="background-color: ${event.layer_color || '#007bff'};">
                                ${showRecurringBadge ? '<span class="recurring-indicator" title="Part of recurring series"></span>' : ''}
                                ${showMovedDot ? '<span class="recurring-indicator moved" title="Moved from series"></span>' : ''}
                                <strong>${event.title}</strong>
                                ${event.location ? `<br><small><i class="fas fa-map-marker-alt me-1"></i>${event.location}</small>` : ''}
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `;
    }

    html += '</div>';
    calendarView.innerHTML = html;
    this.bindCalendarEvents();
}


    renderRecurringView() {
    this.loadRecurringPatterns().then(() => {
        const calendarView = document.getElementById('calendarView');
        
        if (this.recurringPatterns.length === 0) {
            calendarView.innerHTML = `
                <div class="text-center py-5">
                    <i class="fas fa-redo fa-3x text-muted mb-3"></i>
                    <h5 class="text-muted">No Recurring Events</h5>
                    <p class="text-muted">Create an event and check "Recurring Event" to get started.</p>
                </div>
            `;
            return;
        }

        let html = '<div class="recurring-events-list">';

        this.recurringPatterns.forEach(pattern => {
            const recurrenceText = this.getRecurrenceText(pattern);
            const nextOccurrence = this.getNextOccurrence(pattern);
            const layerColor = pattern.layer_color || '#007bff';

            const ex = pattern.exceptions || { counts: { total: 0, moves: 0, deletions: 0 }, moves: [], deletions: [] };

            const exceptionsSummary = ex.counts.total
                ? `<span class="badge bg-warning text-dark ms-2" title="Exceptions">
                     ${ex.counts.total} exception${ex.counts.total > 1 ? 's' : ''}
                   </span>`
                : '';

            const exceptionsDetail = ex.counts.total
                ? `
                  <div class="mt-2 small text-muted">
                    ${ex.counts.moves} moved · ${ex.counts.deletions} skipped
                    <div class="mt-2 border rounded p-2 bg-light">
                      ${
                        ex.moves.map(m => {
                          const orig = new Date(m.original_occurrence_date + 'T00:00');
                          const ns = new Date(m.new_start);
                          const ne = new Date(m.new_end);
                          return `
                            <div class="d-flex align-items-start mb-1">
                              <span class="badge bg-info me-2">Moved</span>
                              <div>
                                <strong>${m.title || pattern.title}</strong>
                                <div>
                                  from <em>${orig.toLocaleDateString()}</em>
                                  to <em>${ns.toLocaleDateString()}</em>
                                  ${ns.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}
                                  – ${ne.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}
                                </div>
                              </div>
                            </div>
                          `;
                        }).join('')
                      }
                      ${
                        ex.deletions.map(d => {
                          const orig = new Date(d.original_occurrence_date + 'T00:00');
                          return `
                            <div class="d-flex align-items-start mb-1">
                              <span class="badge bg-secondary me-2">Skipped</span>
                              <div>originally on <em>${orig.toLocaleDateString()}</em></div>
                            </div>
                          `;
                        }).join('')
                      }
                    </div>
                  </div>
                  `
                : '';

            html += `
                <div class="recurring-event-item">
                    <div class="d-flex align-items-center">
                        <div class="recurring-indicator" style="background-color: ${layerColor}"></div>
                        <div class="flex-grow-1">
                            <div class="recurring-event-title">
                                ${pattern.title} ${exceptionsSummary}
                            </div>
                            <div class="recurring-event-details">
                                <i class="fas fa-clock me-2"></i>${recurrenceText}
                                ${pattern.location ? `<br><i class="fas fa-map-marker-alt me-2"></i>${pattern.location}` : ''}
                                <br><small class="text-muted">Next: ${nextOccurrence}</small>
                                ${exceptionsDetail}
                            </div>
                        </div>
                        <div class="recurring-event-actions">
                            <button class="btn btn-outline-primary btn-sm" onclick="calendar.editEvent('${pattern.id}')">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                            <button class="btn btn-outline-danger btn-sm" onclick="calendar.deleteRecurringEvent('${pattern.id}')">
                                <i class="fas fa-trash"></i> Delete
                            </button>
                        </div>
                    </div>
                </div>
            `;
        });

        html += '</div>';
        calendarView.innerHTML = html;
    });
}

    getRecurrenceText(pattern) {
        const type = pattern.recurrence_type;
        const interval = pattern.recurrence_interval || 1;
        const endType = pattern.recurrence_end_type;
        const endCount = pattern.recurrence_end_count;
        const endDate = pattern.recurrence_end_date;

        let text = '';
        if (interval === 1) {
            text = type === 'daily' ? 'Daily' : type === 'weekly' ? 'Weekly' : 'Monthly';
        } else {
            text = `Every ${interval} ${type === 'daily' ? 'days' : type === 'weekly' ? 'weeks' : 'months'}`;
        }

        if (endType === 'count') {
            text += `, ${endCount} times`;
        } else if (endType === 'date') {
            text += `, until ${new Date(endDate).toLocaleDateString()}`;
        }

        return text;
    }

    getNextOccurrence(pattern) {
        // Backend now stores first_occurrence (date) and start_time separately
        const firstOccurrenceDate = new Date(pattern.first_occurrence);
        const [hours, minutes] = pattern.start_time.split(':');
        firstOccurrenceDate.setHours(parseInt(hours), parseInt(minutes), 0, 0);
        
        const now = new Date();
        let nextDate = new Date(firstOccurrenceDate);

        // Find next occurrence after now
        while (nextDate <= now) {
            const interval = pattern.recurrence_interval || 1;
            if (pattern.recurrence_type === 'daily') {
                nextDate.setDate(nextDate.getDate() + interval);
            } else if (pattern.recurrence_type === 'weekly') {
                nextDate.setDate(nextDate.getDate() + (interval * 7));
            } else if (pattern.recurrence_type === 'monthly') {
                nextDate.setMonth(nextDate.getMonth() + interval);
            }
        }

        return nextDate.toLocaleDateString() + ' at ' + nextDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    }

    bindCalendarEvents() {
        // Add click events for calendar cells
        document.querySelectorAll('.drop-zone').forEach(cell => {
            // Click events - prevent clicks during drag
            cell.addEventListener('click', (e) => {
                if (this.draggedEvent && this.draggedEvent.isDragging) {
                    e.preventDefault();
                    return;
                }

                if (e.target.classList.contains('event')) {
                    const eventId = e.target.getAttribute('data-event-id');
                    this.editEvent(eventId);
                } else {
                    const date = cell.getAttribute('data-date');
                    const hourAttr = cell.getAttribute('data-hour'); // undefined in Month view

                    if (hourAttr == null) {
                        // Month view cell -> open day modal
                        this.openDayModal(date);
                    } else {
                        // Week/Day grid -> create at that hour
                        this.newEvent(date, parseInt(hourAttr, 10));
                    }
                }
            });


            // Drag and drop events
            cell.addEventListener('dragover', this.handleDragOver.bind(this));
            cell.addEventListener('drop', this.handleDrop.bind(this));
            cell.addEventListener('dragenter', this.handleDragEnter.bind(this));
            cell.addEventListener('dragleave', this.handleDragLeave.bind(this));
        });

        // Add drag events for events
        document.querySelectorAll('.event[draggable="true"]').forEach(event => {
            event.addEventListener('dragstart', this.handleDragStart.bind(this));
            event.addEventListener('dragend', this.handleDragEnd.bind(this));
            
            // Prevent default click behavior when dragging
            event.addEventListener('click', (e) => {
                if (this.draggedEvent && this.draggedEvent.isDragging) {
                    e.preventDefault();
                    e.stopPropagation();
                }
            });
        });

        document.querySelectorAll('.month-more').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const ymd = e.currentTarget.getAttribute('data-date');
                this.openDayModal(ymd);
            });
            });
    }

    toLocalYMD(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

    getEventsForDay(date) {
    const dateStr = this.toLocalYMD(date);   // local day
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

    newEvent(date = null, hour = null) {
        this.resetModal();
        document.getElementById('eventModalTitle').textContent = 'New Event';
        
        if (date) {
            const startTime = hour !== null ? 
                `${date}T${hour.toString().padStart(2, '0')}:00` : 
                `${date}T09:00`;
            const endTime = hour !== null ? 
                `${date}T${(hour + 1).toString().padStart(2, '0')}:00` : 
                `${date}T10:00`;
            
            document.getElementById('eventStart').value = startTime;
            document.getElementById('eventEnd').value = endTime;
        }
        
        const modal = new bootstrap.Modal(document.getElementById('eventModal'));
        modal.show();
    }

    editEvent(eventId) {
    const event = this.events.find(e => e.id === eventId);
    if (!event) return console.error('Event not found:', eventId);

    if (event.is_recurring_instance || event.is_recurring_linked) {
        this.currentEditingEvent = event;
        this.showEditRecurringModal();  // lets user pick: single vs series
        return;
    }
    // single event
    this.showEventEditModal(event, 'single');
    }

    showEditRecurringModal() {
        // Create the modal HTML if it doesn't exist
        if (!document.getElementById('editRecurringModal')) {
            this.createEditRecurringModal();
        }
        
        document.getElementById('editSingleInstance').onclick = () => {
            bootstrap.Modal.getInstance(document.getElementById('editRecurringModal')).hide();
            this.showEventEditModal(this.currentEditingEvent, 'single');
        };
        
        document.getElementById('editEntireSeries').onclick = () => {
            bootstrap.Modal.getInstance(document.getElementById('editRecurringModal')).hide();
            // For series editing, we need to load the pattern
            this.editRecurringPattern(this.currentEditingEvent.pattern_id);
        };
        
        const modal = new bootstrap.Modal(document.getElementById('editRecurringModal'));
        modal.show();
    }

    createEditRecurringModal() {
        const modalHTML = `
            <div class="modal fade" id="editRecurringModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Edit Recurring Event</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <p>This is a recurring event. How would you like to edit it?</p>
                            <div class="d-grid gap-2">
                                <button class="btn btn-outline-primary" id="editSingleInstance">
                                    <i class="fas fa-edit me-2"></i>Edit only this occurrence
                                </button>
                                <button class="btn btn-primary" id="editEntireSeries">
                                    <i class="fas fa-redo me-2"></i>Edit entire series
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', modalHTML);
    }

    async editRecurringPattern(patternId) {
    try {
        const res = await fetch(`/api/recurring-patterns/${patternId}`);
        if (!res.ok) throw new Error('Pattern not found');
        const pattern = await res.json();
        this.showPatternEditModal(pattern);
    } catch (err) {
        console.error(err);
        alert('Error loading recurring pattern');
    }
    }


    showPatternEditModal(pattern) {
        // mark we’re editing a series (not a single event)
        this.currentEditType = 'series';

        // stash the series id in the same hidden input
        document.getElementById('eventId').value = pattern.id;

        // populate common fields
        document.getElementById('eventModalTitle').textContent = 'Edit Recurring Series';
        document.getElementById('eventTitle').value = pattern.title || '';
        document.getElementById('eventLocation').value = pattern.location || '';
        document.getElementById('eventDescription').value = pattern.description || '';
        document.getElementById('eventLayer').value = pattern.layer || 'personal';

        // hide date-time and single-instance controls, and remove "required"
        const startRow = document.querySelector('#eventStart').closest('.row');
        const allDayRow = document.querySelector('#allDay').closest('.mb-3');
        startRow.style.display = 'none';
        allDayRow.style.display = 'none';

        // if you ever added required attrs, remove them for series edit
        ['eventStart','eventEnd'].forEach(id => {
            const el = document.getElementById(id);
            el.removeAttribute('required');
            // also disable so the browser ignores it completely
            el.disabled = true;
        });

        // show recurrence options, set values from pattern
        document.getElementById('recurringOptions').style.display = 'block';
        document.getElementById('isRecurring').checked = true;
        document.getElementById('isRecurring').closest('.mb-3').style.display = 'none';

        document.getElementById('recurrenceType').value = pattern.recurrence_type || 'weekly';
        document.getElementById('recurrenceInterval').value = pattern.recurrence_interval || 1;

        const unitEl = document.getElementById('intervalUnit');
        unitEl.textContent = (pattern.recurrence_type === 'daily') ? 'day(s)'
                            : (pattern.recurrence_type === 'monthly') ? 'month(s)'
                            : 'week(s)';

        const endType = pattern.recurrence_end_type || 'never';
        if (endType === 'never') {
            document.getElementById('endNever').checked = true;
        } else if (endType === 'count') {
            document.getElementById('endAfter').checked = true;
            document.getElementById('endAfterCount').value = pattern.recurrence_end_count || 10;
        } else if (endType === 'date') {
            document.getElementById('endOn').checked = true;
            document.getElementById('endOnDate').value = pattern.recurrence_end_date || '';
        }

        document.getElementById('deleteEvent').style.display = 'inline-block';

        const modal = new bootstrap.Modal(document.getElementById('eventModal'));
        modal.show();
        }

    async detachFromSeries(eventId) {
    if (!confirm('Detach this event from its recurring series? Future series edits will not affect it.')) {
        return;
    }
    try {
        const resp = await fetch(`/api/events/${eventId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            is_moved_exception: false,
            original_pattern_id: null,
            original_occurrence_date: null,
            is_recurring_instance: false
        })
        });
        if (!resp.ok) throw new Error('Failed to detach');
        await this.loadEvents();
        const seriesInfo = document.getElementById('seriesInfo');
        if (seriesInfo) seriesInfo.style.display = 'none';
        bootstrap.Modal.getInstance(document.getElementById('eventModal')).hide();
    } catch (e) {
        console.error(e);
        alert('Error detaching from series');
    }
    }
    showEventEditModal(event, editType = 'single') {
    // Keep a reference to the event we’re editing
    this.currentEditingEvent = event;

    // Title
    const titleEl = document.getElementById('eventModalTitle');
    titleEl.textContent = (editType === 'series') ? 'Edit Recurring Series' : 'Edit Event';

    this.currentEditType = editType;

    // Populate fields
    document.getElementById('eventId').value = event.id;
    document.getElementById('eventTitle').value = event.title;
    document.getElementById('eventLocation').value = event.location || '';
    document.getElementById('eventDescription').value = event.description || '';
    document.getElementById('eventLayer').value = event.layer || 'personal';

    document.querySelector('#eventStart').closest('.row').style.display = 'block';
    document.querySelector('#allDay').closest('.mb-3').style.display = 'block';
    document.getElementById('isRecurring').closest('.mb-3').style.display = 'block';

    document.getElementById('eventStart').value = this.formatDateTimeLocal(event.start);
    document.getElementById('eventEnd').value   = this.formatDateTimeLocal(event.end);
    document.getElementById('allDay').checked   = !!event.all_day;

    // ----- Series banner + detach -----
    // Make (or reuse) a banner area just under the modal body
    let seriesInfo = document.getElementById('seriesInfo');
    if (!seriesInfo) {
        seriesInfo = document.createElement('div');
        seriesInfo.id = 'seriesInfo';
        seriesInfo.className = 'alert alert-info py-2 px-3';
        document.querySelector('#eventModal .modal-body').prepend(seriesInfo);
    }
    seriesInfo.style.display = 'none';
    seriesInfo.innerHTML = '';

    // Consider it linked if it’s a generated instance, a moved exception,
    // or the backend attached a `series` object.
    const isSeriesLinked = !!(event.series || event.is_recurring_instance || event.is_moved_exception);

    if (isSeriesLinked) {
        // Hide recurrence-creation UI (this event already belongs to a series)
        document.getElementById('isRecurring').checked = true;
        document.getElementById('recurringOptions').style.display = 'none';

        const s = event.series;
        const recurrenceText = s?.recurrence_text || '';
        const originalDateTxt = event.original_occurrence_date
        ? new Date(event.original_occurrence_date + 'T00:00').toLocaleDateString()
        : null;

        seriesInfo.style.display = 'block';
        seriesInfo.innerHTML = `
        <i class="fas fa-link me-2"></i>
        <strong>Part of series:</strong> ${s ? s.title : '(unknown)'}
        ${recurrenceText ? `&nbsp;<small class="text-muted">(${recurrenceText})</small>` : ''}
        ${originalDateTxt ? `<br><small>Originally scheduled on ${originalDateTxt}</small>` : ''}
        <div class="mt-2">
            <button type="button" class="btn btn-sm btn-outline-secondary" id="detachFromSeriesBtn">
            <i class="fas fa-unlink me-1"></i> Detach from series
            </button>
        </div>
        `;

        // Wire the detach action
        document.getElementById('detachFromSeriesBtn').onclick = () => this.detachFromSeries(event.id);
    } else {
        // Standalone event – hide recurrence UI (only used on create)
        document.getElementById('isRecurring').checked = false;
        document.getElementById('recurringOptions').style.display = 'none';
    }
    // ----------------------------------

    document.getElementById('deleteEvent').style.display = 'inline-block';

    const modal = new bootstrap.Modal(document.getElementById('eventModal'));
    modal.show();
    }


    async saveEvent() {
        const form = document.getElementById('eventForm');

        // If we’re in series mode, temporarily disable any hidden/irrelevant required fields
        const isSeries = this.currentEditType === 'series';
        const disabled = [];
        if (isSeries) {
            ['eventStart','eventEnd','allDay','isRecurring'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { 
                if (el.hasAttribute('required')) disabled.push(el);
                el.removeAttribute('required');
                el.disabled = true;
            }
            });
        }

        if (!form.checkValidity()) {
            form.reportValidity();
            // restore disabled fields before exit
            disabled.forEach(el => { el.setAttribute('required',''); el.disabled = false; });
            return;
        }

        const eventId = document.getElementById('eventId').value || null;
        const editType = this.currentEditType || 'single';

        // Build payload
        const data = {
            title: document.getElementById('eventTitle').value,
            location: document.getElementById('eventLocation').value,
            description: document.getElementById('eventDescription').value,
            layer: document.getElementById('eventLayer').value
        };

        if (editType !== 'series') {
            data.start = document.getElementById('eventStart').value;
            data.end   = document.getElementById('eventEnd').value;
            data.all_day = document.getElementById('allDay').checked;

            data.is_recurring = document.getElementById('isRecurring').checked;
            if (data.is_recurring) {
            const endType = document.querySelector('input[name="recurrenceEnd"]:checked').value;
            data.recurrence_type = document.getElementById('recurrenceType').value;
            data.recurrence_interval = parseInt(document.getElementById('recurrenceInterval').value, 10);
            data.recurrence_end_type = endType;
            if (endType === 'count') data.recurrence_end_count = parseInt(document.getElementById('endAfterCount').value, 10);
            if (endType === 'date')  data.recurrence_end_date  = document.getElementById('endOnDate').value;
            }
        } else {
            // series edit: only recurrence-related fields
            const endType = document.querySelector('input[name="recurrenceEnd"]:checked').value;
            data.recurrence_type = document.getElementById('recurrenceType').value;
            data.recurrence_interval = parseInt(document.getElementById('recurrenceInterval').value, 10);
            data.recurrence_end_type = endType;
            if (endType === 'count') data.recurrence_end_count = parseInt(document.getElementById('endAfterCount').value, 10);
            if (endType === 'date')  data.recurrence_end_date  = document.getElementById('endOnDate').value;
        }

        // Decide endpoint
        let url, method;
        if (editType === 'series') {
            url = eventId ? `/api/recurring-patterns/${eventId}` : '/api/recurring-patterns';
            method = eventId ? 'PUT' : 'POST';
        } else {
            url = eventId ? `/api/events/${eventId}` : '/api/events';
            method = eventId ? 'PUT' : 'POST';
        }

        try {
            const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
            });

            if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.error || `Save failed (${res.status})`);
            }

            await this.loadEvents();
            if (this.currentView === 'recurring') this.render();
            bootstrap.Modal.getInstance(document.getElementById('eventModal')).hide();
        } catch (e) {
            console.error(e);
            alert(`Error saving ${editType === 'series' ? 'series' : 'event'}: ${e.message}`);
        } finally {
            // restore any temporarily disabled fields
            if (isSeries) {
            ['eventStart','eventEnd','allDay','isRecurring'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.disabled = false;
            });
            disabled.forEach(el => el.setAttribute('required',''));
            }
            this.currentEditType = null;
        }
        }


    async deleteEvent() {
        const eventId = document.getElementById('eventId').value;
        const editType = this.currentEditType || 'single';
        
        if (!eventId || !confirm('Are you sure you want to delete this event?')) {
            return;
        }

        try {
            let url;
            if (editType === 'series') {
                url = `/api/recurring-patterns/${eventId}`;
            } else {
                url = `/api/events/${eventId}`;
            }
            
            const response = await fetch(url, {
                method: 'DELETE'
            });

            if (response.ok) {
                await this.loadEvents();
                if (this.currentView === 'recurring') {
                    this.render();
                }
                bootstrap.Modal.getInstance(document.getElementById('eventModal')).hide();
            } else {
                alert('Error deleting event');
            }
        } catch (error) {
            console.error('Error deleting event:', error);
            alert('Error deleting event');
        }
    }

    async deleteRecurringEvent(patternId) {
        if (!confirm('Are you sure you want to delete this recurring event? This will remove the entire series.')) {
            return;
        }

        try {
            const response = await fetch(`/api/recurring-patterns/${patternId}`, {
                method: 'DELETE'
            });

            if (response.ok) {
                await this.loadEvents();
                if (this.currentView === 'recurring') {
                    this.render();
                }
            } else {
                alert('Error deleting recurring event');
            }
        } catch (error) {
            console.error('Error deleting recurring event:', error);
            alert('Error deleting recurring event');
        }
    }

    resetModal() {
        document.getElementById('eventForm').reset();
        document.getElementById('eventId').value = '';
        document.getElementById('deleteEvent').style.display = 'none';
        document.getElementById('eventStart').type = 'datetime-local';
        document.getElementById('eventEnd').type = 'datetime-local';
        document.getElementById('recurringOptions').style.display = 'none';
        document.getElementById('isRecurring').checked = false;
        document.getElementById('endNever').checked = true;
        document.getElementById('intervalUnit').textContent = 'week(s)';
        this.currentEditType = null;
        
        // Show all form fields
        document.querySelector('#eventStart').closest('.row').style.display = 'block';
        document.querySelector('#allDay').closest('.mb-3').style.display = 'block';
        document.getElementById('isRecurring').closest('.mb-3').style.display = 'block';
    }

    // Format a Date -> "YYYY-MM-DDTHH:MM" in *local* time (no timezone)
    toLocalInput(d) {
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }


    // If backend already sent "YYYY-MM-DDTHH:MM", keep it. Otherwise, format local.
    formatDateTimeLocal(value) {
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return value;
    const d = new Date(value);
    return this.toLocalInput(d);
    }

    // Drag and Drop Methods
    handleDragStart(e) {
        this.draggedEvent = {
            id: e.target.getAttribute('data-event-id'),
            element: e.target,
            originalParent: e.target.parentNode
        };
        
        e.target.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/html', e.target.outerHTML);
        
        // Prevent click event when dragging
        setTimeout(() => {
            if (this.draggedEvent) {
                this.draggedEvent.isDragging = true;
            }
        }, 0);
    }

    handleDragEnd(e) {
        e.target.classList.remove('dragging');
        this.clearDragStyles();
    }

    handleDragOver(e) {
        if (this.draggedEvent) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
        }
    }

    handleDragEnter(e) {
        if (this.draggedEvent) {
            // Find the drop zone element
            let dropZone = e.target;
            while (dropZone && !dropZone.classList.contains('drop-zone')) {
                dropZone = dropZone.parentElement;
            }
            
            if (dropZone) {
                dropZone.classList.add('drag-over');
            }
        }
    }

    handleDragLeave(e) {
        if (this.draggedEvent) {
            // Find the drop zone element
            let dropZone = e.target;
            while (dropZone && !dropZone.classList.contains('drop-zone')) {
                dropZone = dropZone.parentElement;
            }
            
            if (dropZone && !dropZone.contains(e.relatedTarget)) {
                dropZone.classList.remove('drag-over');
            }
        }
    }

    handleDrop(e) {
        if (!this.draggedEvent) return;
        
        e.preventDefault();
        e.stopPropagation();
        
        // Find the correct drop zone - traverse up to find the drop-zone element
        let dropZone = e.target;
        while (dropZone && !dropZone.classList.contains('drop-zone')) {
            dropZone = dropZone.parentElement;
        }
        
        if (!dropZone) {
            console.log('No drop zone found');
            this.clearDragStyles();
            return;
        }

        // Double-check we have the right data attributes
        const date = dropZone.getAttribute('data-date');
        const hour = dropZone.getAttribute('data-hour');
        
        if (!date) {
            console.error('No date found on drop zone:', dropZone);
            this.clearDragStyles();
            return;
        }

        this.dropTarget = { date, hour };
        this.clearDragStyles();
        this.showMoveConfirmation();
    }

    clearDragStyles() {
        document.querySelectorAll('.drag-over, .invalid-drop').forEach(el => {
            el.classList.remove('drag-over', 'invalid-drop');
        });
    }

    showMoveConfirmation() {
        const event = this.events.find(e => e.id === this.draggedEvent.id);
        if (!event || !this.dropTarget) return;

        const originalDate = new Date(event.start);
        const originalDateStr = originalDate.toLocaleDateString();
        const originalTimeStr = originalDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

        const newDate = new Date(this.dropTarget.date);
        if (this.dropTarget.hour !== null) {
            newDate.setHours(parseInt(this.dropTarget.hour), 0, 0, 0);
        }
        const newDateStr = newDate.toLocaleDateString();
        const newTimeStr = newDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

        const confirmText = `Move "${event.title}" from ${originalDateStr} ${originalTimeStr} to ${newDateStr} ${newTimeStr}?`;
        document.getElementById('moveConfirmText').textContent = confirmText;

        const modal = new bootstrap.Modal(document.getElementById('moveConfirmModal'));
        modal.show();
    }

    async confirmMoveEvent() {
        if (!this.draggedEvent || !this.dropTarget) return;

        const event = this.events.find(e => e.id === this.draggedEvent.id);
        if (!event) {
            console.error('Event not found in local events:', this.draggedEvent.id);
            return;
        }

        // Check if this is a recurring instance
        if (event.is_recurring_instance) {
            // For recurring instances, we need to:
            // 1. Create a new regular event (exception) for the new date/time
            // 2. Create a deletion exception for the original date to prevent duplicate
            
            // Calculate new start and end times
            const originalStart = new Date(event.start);
            const originalEnd = new Date(event.end);
            const duration = originalEnd.getTime() - originalStart.getTime();

            const newStart = new Date(this.dropTarget.date);
            if (this.dropTarget.hour !== null) {
                newStart.setHours(parseInt(this.dropTarget.hour), originalStart.getMinutes(), 0, 0);
            } else {
                newStart.setHours(originalStart.getHours(), originalStart.getMinutes(), 0, 0);
            }

            const newEnd = new Date(newStart.getTime() + duration);

            try {
                // First, create a deletion exception for the original date
                const deletionException = {
                    title: '[DELETED]',
                    start: event.start,
                    end: event.end,
                    location: '',
                    description: 'Deleted recurring instance',
                    all_day: event.all_day || false,
                    layer: event.layer || 'personal',
                    is_deletion_exception: true,
                    original_pattern_id: event.pattern_id,
                    original_occurrence_date: event.occurrence_date
                };

                await fetch('/api/events', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(deletionException)
                });

                // Then create the moved event as a new exception
                const newEvent = {
                    title: event.title,
                    start: this.toLocalInput(newStart),
                    end:   this.toLocalInput(newEnd),
                    location: event.location || '',
                    description: event.description || '',
                    all_day: event.all_day || false,
                    layer: event.layer || 'personal',
                    is_moved_exception: true,
                    original_pattern_id: event.pattern_id,
                    original_occurrence_date: event.occurrence_date
                };

                const response = await fetch('/api/events', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(newEvent)
                });

                if (response.ok) {
                    await this.loadEvents();
                    bootstrap.Modal.getInstance(document.getElementById('moveConfirmModal')).hide();
                } else {
                    const errorData = await response.json();
                    console.error('Server response:', errorData);
                    alert(`Error moving recurring event: ${errorData.error || 'Unknown error'}`);
                }
            } catch (error) {
                console.error('Error moving recurring event:', error);
                alert('Error moving recurring event');
            }
        } else {
            // Handle regular events normally
            const originalStart = new Date(event.start);
            const originalEnd = new Date(event.end);
            const duration = originalEnd.getTime() - originalStart.getTime();

            const newStart = new Date(this.dropTarget.date);
            if (this.dropTarget.hour !== null) {
                newStart.setHours(parseInt(this.dropTarget.hour), originalStart.getMinutes(), 0, 0);
            } else {
                newStart.setHours(originalStart.getHours(), originalStart.getMinutes(), 0, 0);
            }

            const newEnd = new Date(newStart.getTime() + duration);

            const updatedEvent = {
                title: event.title,
                start: newStart.toISOString().slice(0, 16),
                end: newEnd.toISOString().slice(0, 16),
                location: event.location || '',
                description: event.description || '',
                all_day: event.all_day || false,
                layer: event.layer || 'personal'
            };

            try {
                const response = await fetch(`/api/events/${event.id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(updatedEvent)
                });

                if (response.ok) {
                    await this.loadEvents();
                    bootstrap.Modal.getInstance(document.getElementById('moveConfirmModal')).hide();
                } else {
                    const errorData = await response.json();
                    console.error('Server response:', errorData);
                    alert(`Error moving event: ${errorData.error || 'Unknown error'}`);
                }
            } catch (error) {
                console.error('Error moving event:', error);
                alert('Error moving event');
            }
        }
    }

    async copyEvent() {
        if (!this.draggedEvent || !this.dropTarget) return;

        const originalEvent = this.events.find(e => e.id === this.draggedEvent.id);
        if (!originalEvent) return;

        // Calculate new start and end times
        const originalStart = new Date(originalEvent.start);
        const originalEnd = new Date(originalEvent.end);
        const duration = originalEnd.getTime() - originalStart.getTime();

        const newStart = new Date(this.dropTarget.date);
        if (this.dropTarget.hour !== null) {
            newStart.setHours(parseInt(this.dropTarget.hour), originalStart.getMinutes(), 0, 0);
        } else {
            newStart.setHours(originalStart.getHours(), originalStart.getMinutes(), 0, 0);
        }

        const newEnd = new Date(newStart.getTime() + duration);

        // Create copy of event
        const copiedEvent = {
            title: originalEvent.title + ' (Copy)',
            start: newStart.toISOString().slice(0, 16),
            end: newEnd.toISOString().slice(0, 16),
            location: originalEvent.location,
            description: originalEvent.description,
            all_day: originalEvent.all_day,
            layer: originalEvent.layer
        };

        try {
            const response = await fetch('/api/events', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(copiedEvent)
            });

            if (response.ok) {
                await this.loadEvents();
                bootstrap.Modal.getInstance(document.getElementById('moveConfirmModal')).hide();
            } else {
                alert('Error copying event');
            }
        } catch (error) {
            console.error('Error copying event:', error);
            alert('Error copying event');
        }
    }

    resetDragState() {
        if (this.draggedEvent) {
            this.draggedEvent.isDragging = false;
        }
        // Reset drag state after a short delay to prevent click conflicts
        setTimeout(() => {
            this.draggedEvent = null;
            this.dropTarget = null;
            this.clearDragStyles();
        }, 100);
    }

    // Layer Management Methods
    renderLayersControls() {
        const layersList = document.getElementById('layersList');
        layersList.innerHTML = '';

        this.layers.forEach(layer => {
            const layerItem = document.createElement('div');
            layerItem.className = 'layer-item';
            layerItem.innerHTML = `
                <input type="checkbox" class="form-check-input layer-checkbox" 
                       id="layer-${layer.id}" ${layer.visible ? 'checked' : ''}>
                <div class="layer-color" style="background-color: ${layer.color}" title="Change color"></div>
                <label class="layer-name" for="layer-${layer.id}">${layer.name}</label>
                <button class="layer-delete-btn" data-layer-id="${layer.id}" title="Delete layer">
                    <i class="fas fa-trash"></i>
                </button>
            `;

            // Add toggle event listener
            const checkbox = layerItem.querySelector('.layer-checkbox');
            checkbox.addEventListener('change', (e) => {
                this.toggleLayer(layer.id, e.target.checked);
            });

            // Add delete event listener
            const deleteBtn = layerItem.querySelector('.layer-delete-btn');
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showDeleteLayerModal(layer.id);
            });

            // Add color change listener
            const colorDot = layerItem.querySelector('.layer-color');
            colorDot.addEventListener('click', (e) => {
                e.stopPropagation();
                this.editLayer(layer.id);
            });

            layersList.appendChild(layerItem);
        });
    }

    populateLayerSelect() {
        const layerSelect = document.getElementById('eventLayer');
        layerSelect.innerHTML = '';

        this.layers.forEach(layer => {
            const option = document.createElement('option');
            option.value = layer.id;
            option.textContent = layer.name;
            option.style.color = layer.color;
            layerSelect.appendChild(option);
        });
    }

    async toggleLayer(layerId, visible) {
        try {
            const response = await fetch(`/api/layers/${layerId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ visible })
            });

            if (response.ok) {
                // Update local state
                const layer = this.layers.find(l => l.id === layerId);
                if (layer) {
                    layer.visible = visible;
                }
                // Reload events to apply filtering
                await this.loadEvents();
            } else {
                alert('Error updating layer visibility');
            }
        } catch (error) {
            console.error('Error toggling layer:', error);
            alert('Error updating layer visibility');
        }
    }

    async toggleAllLayers(visible) {
        try {
            const promises = this.layers.map(layer => 
                fetch(`/api/layers/${layer.id}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ visible })
                })
            );

            await Promise.all(promises);
            
            // Update local state
            this.layers.forEach(layer => {
                layer.visible = visible;
            });
            
            // Update UI
            this.renderLayersControls();
            await this.loadEvents();
        } catch (error) {
            console.error('Error toggling all layers:', error);
            alert('Error updating layers');
        }
    }

    // Layer Management Methods
    editLayer(layerId) {
        const layer = this.layers.find(l => l.id === layerId);
        if (!layer) return;

        document.getElementById('layerModalTitle').textContent = 'Edit Layer';
        document.getElementById('layerId').value = layer.id;
        document.getElementById('layerName').value = layer.name;
        document.getElementById('layerVisible').checked = layer.visible;

        // Select the current color
        document.querySelectorAll('.color-option').forEach(opt => {
            opt.classList.remove('selected');
            if (opt.dataset.color === layer.color) {
                opt.classList.add('selected');
                document.getElementById('layerColor').value = layer.color;
            }
        });

        const modal = new bootstrap.Modal(document.getElementById('layerModal'));
        modal.show();
    }

    async saveLayer() {
        const form = document.getElementById('layerForm');
        if (!form.checkValidity()) {
            form.reportValidity();
            return;
        }

        const layerId = document.getElementById('layerId').value;
        const layerData = {
            name: document.getElementById('layerName').value,
            color: document.getElementById('layerColor').value,
            visible: document.getElementById('layerVisible').checked
        };

        try {
            if (layerId) {
                // Update existing layer
                const response = await fetch(`/api/layers/${layerId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(layerData)
                });

                if (!response.ok) throw new Error('Failed to update layer');
            } else {
                // Create new layer
                const response = await fetch('/api/layers', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(layerData)
                });

                if (!response.ok) throw new Error('Failed to create layer');
            }

            // Refresh layers and events
            await this.loadLayers();
            await this.loadEvents();
            bootstrap.Modal.getInstance(document.getElementById('layerModal')).hide();
        } catch (error) {
            console.error('Error saving layer:', error);
            alert('Error saving layer');
        }
    }

    showDeleteLayerModal(layerId) {
        const layer = this.layers.find(l => l.id === layerId);
        if (!layer) return;

        this.layerToDelete = layerId;
        
        // Check if layer has events
        const layerEvents = this.events.filter(event => event.layer === layerId);
        const hasEvents = layerEvents.length > 0;

        document.getElementById('deleteLayerText').textContent = 
            `Are you sure you want to delete "${layer.name}"?`;

        const migrationSection = document.getElementById('layerEventsMigration');
        if (hasEvents) {
            migrationSection.style.display = 'block';
            
            // Populate migration layer dropdown
            const migrationSelect = document.getElementById('migrationLayer');
            migrationSelect.innerHTML = '';
            
            this.layers
                .filter(l => l.id !== layerId)
                .forEach(l => {
                    const option = document.createElement('option');
                    option.value = l.id;
                    option.textContent = l.name;
                    migrationSelect.appendChild(option);
                });
        } else {
            migrationSection.style.display = 'none';
        }

        const modal = new bootstrap.Modal(document.getElementById('deleteLayerModal'));
        modal.show();
    }

    async confirmDeleteLayer() {
        if (!this.layerToDelete) return;

        try {
            const migrationOption = document.querySelector('input[name="migrationOption"]:checked')?.value;
            const migrationLayer = document.getElementById('migrationLayer').value;

            const requestBody = {
                migration_option: migrationOption,
                migration_layer: migrationLayer
            };

            const response = await fetch(`/api/layers/${this.layerToDelete}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestBody)
            });

            if (!response.ok) throw new Error('Failed to delete layer');

            // Refresh layers and events
            await this.loadLayers();
            await this.loadEvents();
            bootstrap.Modal.getInstance(document.getElementById('deleteLayerModal')).hide();
        } catch (error) {
            console.error('Error deleting layer:', error);
            alert('Error deleting layer');
        }
    }

    resetLayerModal() {
        document.getElementById('layerForm').reset();
        document.getElementById('layerId').value = '';
        document.getElementById('layerModalTitle').textContent = 'New Layer';
        document.querySelectorAll('.color-option').forEach(opt => opt.classList.remove('selected'));
        document.getElementById('layerColor').value = '';
    }

    resetDeleteLayerModal() {
        this.layerToDelete = null;
        document.getElementById('moveEvents').checked = true;
        document.getElementById('layerEventsMigration').style.display = 'none';
    }

// Replace your existing openDayModal with this
async openDayModal(date) {
  // 1) set the day the modal should show
  this.dayModalDate = (date instanceof Date) ? new Date(date) : new Date(`${date}T00:00`);

  // 2) (re)render the modal contents (title, ruler, grid, tasks/notes containers)
  this.renderDayModal();
  this.wireDayModalControls();   // <— add this line

  // 3) ---- TASKS sidebar + KANBAN wiring ----
  const ymd = this.toLocalYMD(this.dayModalDate);

  // label
  const labelEl = document.getElementById('tasksDateLabel');
  if (labelEl) labelEl.textContent = ymd;

  // load tasks (API or local) and render the day’s list
  await this.loadTasks();             // <- requires this method from the Kanban snippet
  this.renderDayTasks(ymd);           // <- requires renderDayTasks from the snippet

  // quick-add in sidebar
  const addBtn = document.getElementById('addTaskBtn');
  if (addBtn) addBtn.onclick = () => this.addTaskFromSidebar(ymd); // <- from the snippet

  // open Kanban board
  const kbBtn = document.getElementById('openKanbanBtn');
  if (kbBtn) kbBtn.onclick = () => this.openKanbanModal(ymd);       // <- from the snippet
  // ------------- end tasks wiring -------------

  // 4) show the modal (create instance once)
  if (!this._dayModal) {
    this._dayModal = new bootstrap.Modal(document.getElementById('dayModal'));
  }
  this._dayModal.show();
}

wireDayModalControls() {
  const modal = document.getElementById('dayModal');
  if (!modal) return;

  const prevBtn = modal.querySelector('#dayModalPrev');
  const nextBtn = modal.querySelector('#dayModalNext');
  const newBtn  = modal.querySelector('#dayModalNewEvent');
  const zoomIn  = modal.querySelector('#dayZoomIn');
  const zoomOut = modal.querySelector('#dayZoomOut');

  if (prevBtn) prevBtn.onclick = () => {
    this.dayModalDate = this.dayModalDate || new Date();
    this.dayModalDate.setDate(this.dayModalDate.getDate() - 1);
    this.renderDayModal();
  };

  if (nextBtn) nextBtn.onclick = () => {
    this.dayModalDate = this.dayModalDate || new Date();
    this.dayModalDate.setDate(this.dayModalDate.getDate() + 1);
    this.renderDayModal();
  };

  if (newBtn) newBtn.onclick = () => {
    const ymd = this.toLocalYMD(this.dayModalDate || new Date());
    this.newEvent(ymd); // defaults 09:00–10:00
  };

  if (zoomIn)  zoomIn.onclick  = () => this.setDayZoom(+0.1);
  if (zoomOut) zoomOut.onclick = () => this.setDayZoom(-0.1);
}


renderDayTasks(ymd) {
  const ul = document.getElementById('tasksList');
  const items = this.getTasksForDate(ymd)
    .sort((a,b)=> (a.status||'').localeCompare(b.status||'') || (a.created_at||'').localeCompare(b.created_at||''))
    .map(t => `
      <li class="d-flex align-items-center justify-content-between py-1">
        <div class="task-text">
          <span class="kb-pill me-1">${(t.status||'planned').replace('_',' ')}</span>
          ${t.title}
        </div>
        <button class="task-del btn btn-sm btn-link text-danger p-0" data-task-id="${t.id}">&times;</button>
      </li>
    `);
  ul.innerHTML = items.join('') || `<div class="text-muted small">No tasks yet.</div>`;
  ul.querySelectorAll('.task-del').forEach(btn => {
    btn.onclick = async () => {
      await this.deleteTask(btn.dataset.taskId);
      this.renderDayTasks(ymd);
    };
  });
}

async addTaskFromSidebar(ymd) {
  const input = document.getElementById('addTaskInput');
  const title = (input.value||'').trim();
  if (!title) return;
  const task = {
    id: (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()),
    title,
    details: '',
    date: ymd,
    status: 'planned',
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString()
  };
  await this.createTask(task);
  input.value = '';
  this.renderDayTasks(ymd);
}


renderDaySidebar() {
  const ymd = this.toLocalYMD(this.dayModalDate || new Date());
  // labels
  const opts = { weekday:'long', year:'numeric', month:'long', day:'numeric' };
  const label = (this.dayModalDate || new Date()).toLocaleDateString(undefined, opts);
  const tasksDateLabel = document.getElementById('tasksDateLabel');
  const notesDateLabel = document.getElementById('notesDateLabel');
  if (tasksDateLabel) tasksDateLabel.textContent = label;
  if (notesDateLabel) notesDateLabel.textContent = label;

  // tasks
  const tasksList = document.getElementById('tasksList');
  const addInput  = document.getElementById('addTaskInput');
  const addBtn    = document.getElementById('addTaskBtn');

  let tasks = this._loadTasks(ymd);
  const renderTasks = () => {
    tasksList.innerHTML = tasks.map((t, i) => `
      <li class="${t.done ? 'task-done':''}">
        <input type="checkbox" class="form-check-input" data-i="${i}" ${t.done?'checked':''}>
        <div class="task-text">${t.text}</div>
        <button class="task-del" data-del="${i}" title="Delete">&times;</button>
      </li>
    `).join('');
  };
  renderTasks();

  const addTask = () => {
    const txt = (addInput.value || '').trim();
    if (!txt) return;
    tasks.push({ text: txt, done: false });
    this._saveTasks(ymd, tasks);
    addInput.value = '';
    renderTasks();
  };

  addBtn.onclick = addTask;
  addInput.onkeydown = (e) => { if (e.key === 'Enter') addTask(); };

  tasksList.onclick = (e) => {
    const idxChk = e.target.getAttribute('data-i');
    const idxDel = e.target.getAttribute('data-del');
    if (idxChk !== null) {
      const i = Number(idxChk);
      tasks[i].done = !tasks[i].done;
      this._saveTasks(ymd, tasks);
      renderTasks();
    } else if (idxDel !== null) {
      const i = Number(idxDel);
      tasks.splice(i, 1);
      this._saveTasks(ymd, tasks);
      renderTasks();
    }
  };

  // notes
  const notesArea = document.getElementById('notesTextarea');
  if (notesArea) {
    notesArea.value = this._loadNotes(ymd);
    notesArea.oninput = this._debounce(() => {
      this._saveNotes(ymd, notesArea.value);
    }, 300);
  }
}

// Utility: get or create a Bootstrap modal instance
getOrCreateModal(el) {
  return bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
}

openTaskModal({ ymd, task = null }) {
  const modalEl = document.getElementById('taskEditModal');
  if (!this._taskModal) this._taskModal = new bootstrap.Modal(modalEl);

  // Fields
  const idEl   = modalEl.querySelector('#taskId');
  const nameEl = modalEl.querySelector('#taskName');
  const dueEl  = modalEl.querySelector('#taskDueAt');
  const detEl  = modalEl.querySelector('#taskDetails');
  const stEl   = modalEl.querySelector('#taskStatus');
  const comEl  = modalEl.querySelector('#taskCommittedAt');
  const delBtn = modalEl.querySelector('#taskDeleteBtn');
  const title  = modalEl.querySelector('#taskEditTitle');

  if (task) {
    // edit
    idEl.value       = task.id;
    nameEl.value     = task.title || '';
    dueEl.value      = task.due_at ? task.due_at.slice(0,16) : ''; // assume ISO “YYYY-MM-DDTHH:MM”
    detEl.value      = task.details || '';
    stEl.value       = task.status || 'planned';
    comEl.value      = task.committed_at ? new Date(task.committed_at).toLocaleString() : '';
    delBtn.classList.remove('d-none');
    title.textContent = 'Edit Task';
    delBtn.onclick = async () => {
      if (!confirm('Delete this task?')) return;
      await this.deleteTask(task.id);
      this._taskModal.hide();
      const kEl = document.getElementById('kanbanModal');
      const kYmd = kEl?.dataset.ymd;
      if (kYmd) this.renderKanban(kYmd);
      if (this.dayModalDate) this.renderDayTasks(this.toLocalYMD(this.dayModalDate));
    };
  } else {
    // new
    idEl.value   = '';
    nameEl.value = '';
    dueEl.value  = '';
    detEl.value  = '';
    stEl.value   = 'planned';
    comEl.value  = new Date().toLocaleString(); // committed now
    delBtn.classList.add('d-none');
    title.textContent = 'New Task';
  }

  // Save handler (set once)
  if (!this._taskSaveWired) {
    modalEl.querySelector('#taskEditForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      await this.saveTaskFromModal();
    });
    this._taskSaveWired = true;
  }

  // Remember the date context so we can re-render that lane/day
  modalEl.dataset.ymd = ymd || (document.getElementById('kanbanModal')?.dataset.ymd) || this.toLocalYMD(new Date());

  this._taskModal.show();
}

async saveTaskFromModal() {
  const modalEl = document.getElementById('taskEditModal');
  const id   = modalEl.querySelector('#taskId').value || null;
  const ymd  = modalEl.dataset.ymd;
  const body = {
    title:  modalEl.querySelector('#taskName').value.trim(),
    details:modalEl.querySelector('#taskDetails').value.trim(),
    due_at: modalEl.querySelector('#taskDueAt').value ? new Date(modalEl.querySelector('#taskDueAt').value).toISOString() : null,
    status: modalEl.querySelector('#taskStatus').value || 'planned',
    date:   ymd,
  };

  if (!body.title) { alert('Task name is required'); return; }

  if (id) {
    await this.updateTask(id, { ...body, updated_at: new Date().toISOString() });
  } else {
    // set committed_at on create
    await this.createTask({ ...body, committed_at: new Date().toISOString() });
  }

  this._taskModal.hide();

  // refresh UI
  const kEl = document.getElementById('kanbanModal');
  const kYmd = kEl?.dataset.ymd || ymd;
  if (kYmd) this.renderKanban(kYmd);
  if (this.dayModalDate) this.renderDayTasks(this.toLocalYMD(this.dayModalDate));
}

// Call this when clicking "Open board" in the day modal
async openKanbanModal(ymd) {
  // 1) Resolve date context
  const dateStr = ymd || (this.dayModalDate ? this.toLocalYMD(this.dayModalDate) : this.toLocalYMD(new Date()));

  // 2) Hide the day modal underneath (avoid double backdrop)
  const dayEl = document.getElementById('dayModal');
  const dayInst = dayEl ? bootstrap.Modal.getInstance(dayEl) : null;
  if (dayInst) dayInst.hide();

  // 3) Prepare Kanban modal
  const kbEl = document.getElementById('kanbanModal');
  kbEl.dataset.ymd = dateStr; // remember which day this board is for
  document.getElementById('kanbanTitle').textContent = `Tasks Board — ${dateStr}`;

  const kbModal = this.getOrCreateModal(kbEl);

  // When Kanban closes, restore the day modal (optional)
  const onHidden = () => {
    kbEl.removeEventListener('hidden.bs.modal', onHidden);
    if (dayInst) dayInst.show();
  };
  kbEl.addEventListener('hidden.bs.modal', onHidden);

  // 4) Wire actions (assign .onclick so we don't stack multiple listeners)
  // New Task button (always open the rich task editor)
  const kbNewTaskBtn = document.getElementById('kbNewTaskBtn');
  if (kbNewTaskBtn) {
    kbNewTaskBtn.onclick = () => this.openTaskModal({ ymd: dateStr });
  }

  // Quick Add row -> open the task editor prefilled with row inputs
  const addBtn = document.getElementById('kbAdd');
  if (addBtn) {
    addBtn.onclick = () => {
      const title   = (document.getElementById('kbTitle')?.value || '').trim();
      const details = (document.getElementById('kbDetails')?.value || '').trim();
      const when    = (document.getElementById('kbWhen')?.value || '').trim();
      const status  = (document.getElementById('kbStatus')?.value || 'Planned');

      this.openTaskModal({
        ymd: dateStr,
        task: {
          // pass as a draft to prefill the edit modal
          id: null,
          title,
          details,
          status: status.toLowerCase().replace(' ', '_'), // normalize to planned/started/in_progress/completed
          due_at: when ? new Date(when).toISOString() : null
        }
      });
    };
  }

  // 5) Zoom controls (persist across opens)
  const zoomOut = document.getElementById('kanbanZoomOut');
  const zoomIn  = document.getElementById('kanbanZoomIn');
  const zoomLbl = document.getElementById('kanbanZoomLabel');
  const board   = document.getElementById('kanbanBoard');

  this.kanbanZoom = this.kanbanZoom ?? 1;
  const applyZoom = () => {
    // CSS zoom keeps scrollbars & hit-testing aligned
    board.style.zoom = this.kanbanZoom;
    zoomLbl.textContent = `${Math.round(this.kanbanZoom * 100)}%`;
  };
  if (zoomOut) zoomOut.onclick = () => { this.kanbanZoom = Math.max(0.7, this.kanbanZoom - 0.1); applyZoom(); };
  if (zoomIn)  zoomIn.onclick  = () => { this.kanbanZoom = Math.min(1.5, this.kanbanZoom + 0.1); applyZoom(); };
  applyZoom();

  // 6) Fetch tasks and render
  await this.loadTasks();          // make sure this.tasks is fresh
  this.renderKanban(dateStr);      // your fixed renderer (with data-id on cards, guards in ondrop)

  // 7) Show the modal
  kbModal.show();
}


renderKanban(ymd) {
  // Partition by status
  const by = { planned: [], started: [], in_progress: [], completed: [] };
  this.getTasksForDate(ymd).forEach(t => {
    const k = (t.status || 'planned');
    (by[k] || by.planned).push(t);
  });

  // counts
  const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = String(v); };
  setTxt('kbCntPlanned',  by.planned.length);
  setTxt('kbCntStarted',  by.started.length);
  setTxt('kbCntProgress', by.in_progress.length);
  setTxt('kbCntDone',     by.completed.length);

  const cardHTML = (t) => `
    <div class="kb-card" draggable="true" data-id="${t.id}">
      <div class="kb-card-title">${this.escapeHtml(t.title || '(untitled)')}</div>
      <div class="kb-card-meta">
        ${t.due_at ? `Due: ${new Date(t.due_at).toLocaleString()}` : ''}
      </div>
      <div class="kb-card-actions mt-1">
        <button class="btn btn-sm btn-outline-secondary kb-edit" data-id="${t.id}">Edit</button>
        <button class="btn btn-sm btn-outline-danger kb-del" data-id="${t.id}">Delete</button>
      </div>
    </div>
  `;

  const mount = (bodyId, items) => {
    const body = document.getElementById(bodyId);
    if (!body) return;
    body.innerHTML = items.map(cardHTML).join('');

    // drag
    body.querySelectorAll('.kb-card').forEach(card => {
      card.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', card.dataset.id || '');
      });
    });

    // edit/delete
    body.querySelectorAll('.kb-edit').forEach(btn => {
      btn.onclick = () => {
        const t = this.tasks.find(x => x.id === btn.dataset.id);
        if (t) this.openTaskModal({ ymd, task: t });
      };
    });
    body.querySelectorAll('.kb-del').forEach(btn => {
      btn.onclick = async () => {
        const t = this.tasks.find(x => x.id === btn.dataset.id);
        if (!t) return;
        if (!confirm('Delete this task?')) return;
        await this.deleteTask(t.id);
        this.renderKanban(ymd);
        this.renderDayTasks(ymd);
      };
    });

    // drop target (on the column body’s parent .kb-col)
    const col = body.closest('.kb-col');
    const newStatus = col?.dataset.status;

    body.ondragover  = (e) => { e.preventDefault(); col?.classList.add('drag-over'); };
    body.ondragleave = ()  => { col?.classList.remove('drag-over'); };
    body.ondrop = async (e) => {
      e.preventDefault();
      col?.classList.remove('drag-over');
      const id = e.dataTransfer.getData('text/plain');
      if (!id) return;                     // <-- guard against undefined
      if (!newStatus) return;
      const task = this.tasks.find(x => x.id === id);
      if (!task) return;
      if (task.status === newStatus) return;

      // Optional confirm
      if (!confirm(`Move "${task.title}" to ${newStatus.replace('_',' ')}?`)) return;

      await this.updateTask(id, { status: newStatus, updated_at: new Date().toISOString() });
      this.renderKanban(ymd);
      this.renderDayTasks(ymd);
    };
  };

  mount('kbPlanned',  by.planned);
  mount('kbStarted',  by.started);
  mount('kbProgress', by.in_progress);
  mount('kbDone',     by.completed);
}

renderDayModal() {
  const modalEl  = document.getElementById('dayModal');
  const titleEl  = modalEl.querySelector('.day-modal-title');
  const scrollEl = modalEl.querySelector('.day-modal-body'); // instead of .day-calendar-scroll
  const rulerEl  = modalEl.querySelector('.day-modal-ruler');     // ← hour labels column
  const gridEl   = modalEl.querySelector('.day-modal-grid');      // ← absolute event canvas

  // ---- zoom / sizing ----
  const PX_PER_MIN  = this.dayZoom || 1;       // e.g. 0.8, 1, 1.2
  const DAY_MINUTES = 24 * 60;
  const HOUR_PX     = 60 * PX_PER_MIN;

  // apply to CSS-driven background stripes
  gridEl.style.setProperty('--hourH', `${HOUR_PX}px`);
  // set total grid height (px)
  gridEl.style.height = `${DAY_MINUTES * PX_PER_MIN}px`;

  // ---- header ----
  const d = this.dayModalDate || new Date();
  titleEl.textContent = d.toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });

  // ---- build hour ruler ----
  const hoursHtml = [];
  for (let h = 0; h < 24; h++) {
    const label = new Date(d.getFullYear(), d.getMonth(), d.getDate(), h, 0, 0)
      .toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    hoursHtml.push(`
      <div class="day-hour-row" style="height:${HOUR_PX}px">
        <div class="day-hour-label">${label}</div>
      </div>
    `);
  }
  rulerEl.innerHTML = hoursHtml.join('');

  // ---- clear grid ----
  gridEl.innerHTML = '';

  // helpers
  const y = d.getFullYear(), m = d.getMonth(), day = d.getDate();
  const startOfDay = new Date(y, m, day, 0, 0, 0, 0);
  const minsFromMidnight = (dt) =>
    Math.max(0, Math.min(DAY_MINUTES, Math.round((dt - startOfDay) / 60000)));

  // ---- collect today's events with metadata ----
  const todays = this.getEventsForDay(d).map(ev => {
    const s = new Date(ev.start);
    const e = new Date(ev.end);
    const startMin = minsFromMidnight(s);
    const endMin   = Math.max(startMin + 15, minsFromMidnight(e)); // min 15m duration
    return { ev, s, e, startMin, endMin, col: 0, cols: 1 };
  });

  // sort for grouping
  todays.sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin);

  // ---- group overlapping events into clusters ----
  const groups = [];
  for (const item of todays) {
    let placed = false;
    for (const g of groups) {
      const overlaps = g.some(x => !(item.endMin <= x.startMin || x.endMin <= item.startMin));
      if (overlaps) { g.push(item); placed = true; break; }
    }
    if (!placed) groups.push([item]);
  }

  // ---- assign columns per group (greedy) ----
  for (const group of groups) {
    const activeEnds = []; // end minute per column, or null if free
    for (const item of group) {
      for (let c = 0; c < activeEnds.length; c++) {
        if (activeEnds[c] !== null && activeEnds[c] <= item.startMin) activeEnds[c] = null;
      }
      let colIdx = activeEnds.findIndex(v => v === null);
      if (colIdx === -1) { colIdx = activeEnds.length; activeEnds.push(null); }
      item.col = colIdx;
      activeEnds[colIdx] = item.endMin;
    }
    const totalCols = Math.max(1, activeEnds.length);
    group.forEach(it => it.cols = totalCols);
  }

  // ---- render events using real grid width (so gaps are pixel-accurate) ----
  const GAP_PX = 6;
  const PAD_L  = 8;
  const PAD_R  = 8;
  const gridRect = gridEl.getBoundingClientRect();
  const innerWidth = Math.max(0, gridRect.width - PAD_L - PAD_R);

  let firstTopPx = null;

  groups.flat().forEach(item => {
    const { ev, s, e, startMin, endMin, col, cols } = item;

    const totalGap = (cols - 1) * GAP_PX;
    const colWidth = Math.max(40, (innerWidth - totalGap) / cols);
    const leftPx   = PAD_L + col * (colWidth + GAP_PX);

    const topPx    = startMin * PX_PER_MIN;
    const heightPx = Math.max(15 * PX_PER_MIN, (endMin - startMin) * PX_PER_MIN);

    const node = document.createElement('div');
    node.className = 'day-modal-event';
    node.style.top    = `${topPx}px`;
    node.style.height = `${heightPx}px`;
    node.style.left   = `${leftPx}px`;
    node.style.width  = `${colWidth}px`;
    node.style.backgroundColor = ev.layer_color || '#28a745';
    node.setAttribute('data-event-id', ev.id);

    const badge = ev.is_recurring_linked ? '<span class="recurring-indicator"></span>' : '';
    const moved = ev.is_moved_exception  ? '<span class="recurring-indicator moved" title="Moved from series"></span>' : '';

    node.innerHTML = `
      <div class="day-modal-event-title">
        ${badge}${moved}${ev.title}
      </div>
      <div class="day-modal-event-time">
        ${s.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}
        &nbsp;&ndash;&nbsp;
        ${e.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}
      </div>
    `;
    node.addEventListener('click', () => this.editEvent(ev.id));
    gridEl.appendChild(node);

    if (firstTopPx === null) firstTopPx = topPx;
  });

  // ---- scroll to first event (or 8am if none) ----
  const target = (firstTopPx ?? (8 * 60 * PX_PER_MIN)) - 40;
  scrollEl.scrollTop = Math.max(0, target);
}

// ===== Task store =====
tasks = [];

// --- API helpers with localStorage fallback
async loadTasks(date /* optional */) {
  try {
    const url = date ? `/api/tasks?date=${encodeURIComponent(date)}` : '/api/tasks';
    const res = await fetch(url);
    this.tasks = res.ok ? await res.json() : JSON.parse(localStorage.getItem('tasks') || '[]');
  } catch {
    this.tasks = JSON.parse(localStorage.getItem('tasks') || '[]');
  }
}

saveTasksLocally() {
  localStorage.setItem('tasks', JSON.stringify(this.tasks));
}

async createTask(payload) {
  const res = await fetch('/api/tasks', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error('createTask failed');
  const created = await res.json();   // { id, ... }
  this.tasks.push(created);
  return created;
}

async updateTask(id, patch) {
  const res = await fetch(`/api/tasks/${id}`, {
    method: 'PATCH', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(patch)
  });
  if (!res.ok) throw new Error('updateTask failed');
  const updated = await res.json();
  const i = this.tasks.findIndex(t => t.id === id);
  if (i !== -1) this.tasks[i] = updated;
  return updated;
}

async deleteTask(id) {
  try {
    const res = await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error();
  } catch {/* ignore */}
  this.tasks = this.tasks.filter(t => t.id !== id);
  this.saveTasksLocally();
}

// --- Utilities
toLocalYMD(d) {
  const y = d.getFullYear(), m = d.getMonth()+1, day = d.getDate();
  return `${y}-${String(m).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
}

getTasksForDate(ymd) {
  return this.tasks.filter(t => t.date === ymd);
}

}

// Initialize calendar when page loads
let calendar;
document.addEventListener('DOMContentLoaded', () => {
    calendar = new Calendar();
});

document.getElementById('sendBtn').addEventListener('click', sendMessage);
document.getElementById('chatInput').addEventListener('keypress', e => {
  if (e.key === 'Enter') sendMessage();
});

function sendMessage() {
  const input = document.getElementById('chatInput');
  const text = input.value.trim();
  if (!text) return;

  appendMessage('user', text);
  input.value = '';

  // Fake assistant response
  setTimeout(() => {
    appendMessage('assistant', "I'm here to help with your calendar!");
  }, 800);
}

function appendMessage(role, text) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;
  msg.textContent = text;
  document.getElementById('chatMessages').appendChild(msg);

  // Auto scroll
  msg.scrollIntoView({ behavior: 'smooth' });
}
