// calendar-renderer.js - Calendar Rendering Module
class CalendarRenderer {
  constructor(calendar) {
    this.calendar = calendar;
  }

  updateDateDisplay() {
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ];
    const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

    let displayText;
    switch(this.calendar.currentView) {
      case 'month':
        displayText = `${monthNames[this.calendar.currentDate.getMonth()]} ${this.calendar.currentDate.getFullYear()}`;
        break;
      case 'week':
        const weekStart = this.calendar.getWeekStart(this.calendar.currentDate);
        const weekEnd = new Date(weekStart);
        weekEnd.setDate(weekEnd.getDate() + 6);
        if (weekStart.getMonth() === weekEnd.getMonth()) {
          displayText = `${monthNames[weekStart.getMonth()]} ${weekStart.getDate()} - ${weekEnd.getDate()}, ${weekStart.getFullYear()}`;
        } else {
          displayText = `${monthNames[weekStart.getMonth()]} ${weekStart.getDate()} - ${monthNames[weekEnd.getMonth()]} ${weekEnd.getDate()}, ${weekStart.getFullYear()}`;
        }
        break;
      case 'day':
        displayText = `${dayNames[this.calendar.currentDate.getDay()]}, ${monthNames[this.calendar.currentDate.getMonth()]} ${this.calendar.currentDate.getDate()}, ${this.calendar.currentDate.getFullYear()}`;
        break;
      case 'recurring':
        displayText = 'Recurring Events';
        break;
    }
    document.getElementById('currentMonth').textContent = displayText;
  }

  updateViewButtons() {
    document.querySelectorAll('.view-buttons .btn').forEach(btn => {
      btn.classList.remove('active');
    });
    document.getElementById(`${this.calendar.currentView}View`).classList.add('active');
  }

  renderCurrentView() {
    switch(this.calendar.currentView) {
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

  renderMonthView() {
    const calendarView = document.getElementById('calendarView');
    const firstDay = new Date(this.calendar.currentDate.getFullYear(), this.calendar.currentDate.getMonth(), 1);
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
        const isCurrentMonth = cellDate.getMonth() === this.calendar.currentDate.getMonth();
        const isToday = cellDate.toDateString() === today.toDateString();
        const dayEvents = this.calendar.getEventsForDay(cellDate);

        let dayClass = 'calendar-day';
        if (!isCurrentMonth) dayClass += ' other-month';
        if (isToday) dayClass += ' today';

        const dateString = this.calendar.toLocalYMD(cellDate);
        const sorted = [...dayEvents].sort((a, b) => new Date(a.start) - new Date(b.start));
        const MAX = this.getMaxEventsPerCell();
        const visible = sorted.slice(0, MAX);
        const hiddenCount = Math.max(0, sorted.length - visible.length);

        html += `
          <div class="col ${dayClass} drop-zone" data-date="${dateString}" title="Date: ${dateString}">
            <div class="day-number">${cellDate.getDate()}</div>
            ${visible.map(ev => this.renderMonthEvent(ev)).join('')}
            ${hiddenCount > 0 ? `<button type="button" class="month-more btn btn-link p-0" data-date="${dateString}">+${hiddenCount} more</button>` : ''}
          </div>
        `;
        startDate.setDate(startDate.getDate() + 1);
      }
      html += '</div>';
    }

    html += '</div>';
    calendarView.innerHTML = html;
    this.bindCalendarEvents();
  }

  renderMonthEvent(ev) {
    const showRecurringBadge = !!ev.is_recurring_linked;
    const showMovedDot = !!ev.is_moved_exception;
    const isAllDay = !!ev.all_day;
    const timeText = isAllDay ? '' : this.calendar.formatHHMM(ev.start);
    const titleAttr = isAllDay ? ev.title : `${this.calendar.formatHHMM(ev.start)}–${this.calendar.formatHHMM(ev.end)} · ${ev.title}`;

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
  }

  renderWeekView() {
    const calendarView = document.getElementById('calendarView');
    const weekStart = this.calendar.getWeekStart(this.calendar.currentDate);
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
      const timeStr = this.formatTimeLabel(hour);
      html += `<div class="col-1 p-2 text-end" style="font-size: 0.8rem; color: #666; border-right: 1px solid var(--border-color);">${timeStr}</div>`;

      for (let i = 0; i < 7; i++) {
        const day = new Date(weekStart);
        day.setDate(day.getDate() + i);
        const dayEvents = this.calendar.getEventsForHour(day, hour);
        const isToday = day.toDateString() === today.toDateString();

        html += `
          <div class="col week-day-cell drop-zone ${isToday ? 'today' : ''}" 
               data-date="${this.calendar.toLocalYMD(day)}" 
               data-hour="${hour}" 
               style="border-right: 1px solid var(--border-color); cursor: pointer; position: relative;">
            ${dayEvents.map(event => this.renderWeekEvent(event)).join('')}
          </div>
        `;
      }
      html += '</div>';
    }

    html += '</div>';
    calendarView.innerHTML = html;
    this.bindCalendarEvents();
  }

  renderWeekEvent(event) {
    const showRecurringBadge = event.is_recurring_linked;
    const showMovedDot = event.is_moved_exception;
    return `
      <div class="event ${showRecurringBadge ? 'recurring-event' : ''}" 
           draggable="true" 
           data-event-id="${event.id}" 
           style="position: absolute; top: 2px; left: 2px; right: 2px; z-index: 2; background-color: ${event.layer_color || '#007bff'};">
        ${showRecurringBadge ? '<span class="recurring-indicator" title="Part of recurring series"></span>' : ''}
        ${showMovedDot ? '<span class="recurring-indicator moved" title="Moved from series"></span>' : ''}
        ${event.title}
      </div>
    `;
  }

  renderDayView() {
    const calendarView = document.getElementById('calendarView');
    const today = new Date();
    const isToday = this.calendar.currentDate.toDateString() === today.toDateString();

    let html = `
      <div class="calendar-grid">
        <div class="row calendar-header-row g-0">
          <div class="col-2 calendar-header-cell">Time</div>
          <div class="col calendar-header-cell ${isToday ? 'text-primary fw-bold' : ''}">
            ${this.calendar.currentDate.toLocaleDateString('en-US', { 
              weekday: 'long', 
              month: 'long', 
              day: 'numeric' 
            })}
          </div>
        </div>
    `;

    for (let hour = 0; hour < 24; hour++) {
      const timeStr = this.formatTimeLabel(hour, true);
      const dayEvents = this.calendar.getEventsForHour(this.calendar.currentDate, hour);

      html += `
        <div class="row g-0" style="min-height: 80px; border-bottom: 1px solid var(--border-color);">
          <div class="col-2 p-3 text-end" style="font-size: 0.9rem; color: #666; border-right: 1px solid var(--border-color);">
            ${timeStr}
          </div>
          <div class="col day-hour-cell drop-zone ${isToday ? 'today' : ''}" 
               data-date="${this.calendar.currentDate.toISOString().split('T')[0]}" 
               data-hour="${hour}" 
               style="cursor: pointer; position: relative; padding: 0.5rem;">
            ${dayEvents.map(event => this.renderDayEvent(event)).join('')}
          </div>
        </div>
      `;
    }

    html += '</div>';
    calendarView.innerHTML = html;
    this.bindCalendarEvents();
  }

  renderDayEvent(event) {
    const showRecurringBadge = event.is_recurring_linked;
    const showMovedDot = event.is_moved_exception;
    return `
      <div class="event mb-1 ${showRecurringBadge ? 'recurring-event' : ''}" 
           draggable="true" 
           data-event-id="${event.id}" 
           style="background-color: ${event.layer_color || '#007bff'};">
        ${showRecurringBadge ? '<span class="recurring-indicator" title="Part of recurring series"></span>' : ''}
        ${showMovedDot ? '<span class="recurring-indicator moved" title="Moved from series"></span>' : ''}
        <strong>${event.title}</strong>
        ${event.location ? `<br><small><i class="fas fa-map-marker-alt me-1"></i>${event.location}</small>` : ''}
      </div>
    `;
  }

  renderRecurringView() {
    this.calendar.loadRecurringPatterns().then(() => {
      const calendarView = document.getElementById('calendarView');
      
      if (this.calendar.recurringPatterns.length === 0) {
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
      this.calendar.recurringPatterns.forEach(pattern => {
        html += this.renderRecurringPattern(pattern);
      });
      html += '</div>';
      calendarView.innerHTML = html;
    });
  }

  renderRecurringPattern(pattern) {
    const recurrenceText = this.getRecurrenceText(pattern);
    const nextOccurrence = this.getNextOccurrence(pattern);
    const layerColor = pattern.layer_color || '#007bff';
    const ex = pattern.exceptions || { counts: { total: 0, moves: 0, deletions: 0 }, moves: [], deletions: [] };
    
    const exceptionsSummary = ex.counts.total ? 
      `<span class="badge bg-warning text-dark ms-2" title="Exceptions">${ex.counts.total} exception${ex.counts.total > 1 ? 's' : ''}</span>` : '';

    return `
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
            </div>
          </div>
          <div class="recurring-event-actions">
            <button class="btn btn-outline-primary btn-sm" onclick="calendar.eventManager.editEvent('${pattern.id}')">
              <i class="fas fa-edit"></i> Edit
            </button>
            <button class="btn btn-outline-danger btn-sm" onclick="calendar.eventManager.deleteRecurringEvent('${pattern.id}')">
              <i class="fas fa-trash"></i> Delete
            </button>
          </div>
        </div>
      </div>
    `;
  }

  // Helper methods
  getMaxEventsPerCell() {
    const calendarView = document.getElementById('calendarView');
    const row = calendarView.querySelector('.calendar-day');
    if (!row) return 3;

    const cellHeight = row.offsetHeight;
    const approxEventHeight = 22;
    const maxByHeight = Math.floor((cellHeight - 20) / approxEventHeight);

    const w = window.innerWidth;
    let maxByWidth = 3;
    if (w < 576) maxByWidth = 2;
    if (w >= 992) maxByWidth = 4;

    return Math.min(maxByHeight, maxByWidth);
  }

  formatTimeLabel(hour, showMinutes = false) {
    if (hour === 0) return showMinutes ? '12:00 AM' : '12 AM';
    if (hour < 12) return showMinutes ? `${hour}:00 AM` : `${hour} AM`;
    if (hour === 12) return showMinutes ? '12:00 PM' : '12 PM';
    return showMinutes ? `${hour - 12}:00 PM` : `${hour - 12} PM`;
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
    const firstOccurrenceDate = new Date(pattern.first_occurrence);
    const [hours, minutes] = pattern.start_time.split(':');
    firstOccurrenceDate.setHours(parseInt(hours), parseInt(minutes), 0, 0);

    const now = new Date();
    let nextDate = new Date(firstOccurrenceDate);

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

    return nextDate.toLocaleDateString() + ' at ' + 
           nextDate.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
  }

  bindCalendarEvents() {
    // Click events for calendar cells
    document.querySelectorAll('.drop-zone').forEach(cell => {
      cell.addEventListener('click', (e) => {
        if (this.calendar.dragDrop.draggedEvent && this.calendar.dragDrop.draggedEvent.isDragging) {
          e.preventDefault();
          return;
        }

        if (e.target.classList.contains('event')) {
          const eventId = e.target.getAttribute('data-event-id');
          this.calendar.eventManager.editEvent(eventId);
        } else {
          const date = cell.getAttribute('data-date');
          const hourAttr = cell.getAttribute('data-hour');
          
          if (hourAttr == null) {
            this.calendar.dayModal.openDayModal(date);
          } else {
            this.calendar.eventManager.newEvent(date, parseInt(hourAttr, 10));
          }
        }
      });

      // Bind drag and drop events
      this.calendar.dragDrop.bindDropEvents(cell);
    });

    // Bind drag events for events
    document.querySelectorAll('.event[draggable="true"]').forEach(event => {
      this.calendar.dragDrop.bindDragEvents(event);
    });

    // "+N more" buttons
    document.querySelectorAll('.month-more').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const ymd = e.currentTarget.getAttribute('data-date');
        this.calendar.dayModal.openDayModal(ymd);
      });
    });
  }
}