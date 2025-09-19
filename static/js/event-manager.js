// event-manager.js - Event Management Module
class EventManager {
  constructor(calendar) {
    this.calendar = calendar;
  }

  bindEventHandlers() {
    // Event form handlers
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

    // Form field handlers
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
      recurringOptions.style.display = e.target.checked ? 'block' : 'none';
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

    // Modal event handlers
    document.getElementById('eventModal').addEventListener('hidden.bs.modal', () => {
      this.resetModal();
    });

    document.getElementById('moveConfirmModal').addEventListener('hidden.bs.modal', () => {
      this.calendar.dragDrop.resetDragState();
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
    const event = this.calendar.events.find(e => e.id === eventId);
    if (!event) return console.error('Event not found:', eventId);

    if (event.is_recurring_instance || event.is_recurring_linked) {
      this.calendar.currentEditingEvent = event;
      this.showEditRecurringModal();
      return;
    }

    this.showEventEditModal(event, 'single');
  }

  showEditRecurringModal() {
    if (!document.getElementById('editRecurringModal')) {
      this.createEditRecurringModal();
    }

    document.getElementById('editSingleInstance').onclick = () => {
      bootstrap.Modal.getInstance(document.getElementById('editRecurringModal')).hide();
      this.showEventEditModal(this.calendar.currentEditingEvent, 'single');
    };

    document.getElementById('editEntireSeries').onclick = () => {
      bootstrap.Modal.getInstance(document.getElementById('editRecurringModal')).hide();
      this.editRecurringPattern(this.calendar.currentEditingEvent.pattern_id);
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
    this.calendar.currentEditType = 'series';
    document.getElementById('eventId').value = pattern.id;
    document.getElementById('eventModalTitle').textContent = 'Edit Recurring Series';
    document.getElementById('eventTitle').value = pattern.title || '';
    document.getElementById('eventLocation').value = pattern.location || '';
    document.getElementById('eventDescription').value = pattern.description || '';
    document.getElementById('eventLayer').value = pattern.layer || 'personal';

    // Hide date-time controls for series editing
    const startRow = document.querySelector('#eventStart').closest('.row');
    const allDayRow = document.querySelector('#allDay').closest('.mb-3');
    startRow.style.display = 'none';
    allDayRow.style.display = 'none';

    // Show recurrence options
    document.getElementById('recurringOptions').style.display = 'block';
    document.getElementById('isRecurring').checked = true;
    document.getElementById('isRecurring').closest('.mb-3').style.display = 'none';
    
    this.populateRecurrenceFields(pattern);
    document.getElementById('deleteEvent').style.display = 'inline-block';

    const modal = new bootstrap.Modal(document.getElementById('eventModal'));
    modal.show();
  }

  populateRecurrenceFields(pattern) {
    document.getElementById('recurrenceType').value = pattern.recurrence_type || 'weekly';
    document.getElementById('recurrenceInterval').value = pattern.recurrence_interval || 1;
    
    const unitEl = document.getElementById('intervalUnit');
    unitEl.textContent = (pattern.recurrence_type === 'daily') ? 'day(s)' : 
                        (pattern.recurrence_type === 'monthly') ? 'month(s)' : 'week(s)';

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
  }

  showEventEditModal(event, editType = 'single') {
    this.calendar.currentEditingEvent = event;
    this.calendar.currentEditType = editType;

    document.getElementById('eventModalTitle').textContent = 'Edit Event';
    document.getElementById('eventId').value = event.id;
    document.getElementById('eventTitle').value = event.title;
    document.getElementById('eventLocation').value = event.location || '';
    document.getElementById('eventDescription').value = event.description || '';
    document.getElementById('eventLayer').value = event.layer || 'personal';

    // Show form fields
    document.querySelector('#eventStart').closest('.row').style.display = 'block';
    document.querySelector('#allDay').closest('.mb-3').style.display = 'block';
    document.getElementById('isRecurring').closest('.mb-3').style.display = 'block';

    document.getElementById('eventStart').value = this.formatDateTimeLocal(event.start);
    document.getElementById('eventEnd').value = this.formatDateTimeLocal(event.end);
    document.getElementById('allDay').checked = !!event.all_day;

    this.handleSeriesInfo(event);
    document.getElementById('deleteEvent').style.display = 'inline-block';

    const modal = new bootstrap.Modal(document.getElementById('eventModal'));
    modal.show();
  }

  handleSeriesInfo(event) {
    let seriesInfo = document.getElementById('seriesInfo');
    if (!seriesInfo) {
      seriesInfo = document.createElement('div');
      seriesInfo.id = 'seriesInfo';
      seriesInfo.className = 'alert alert-info py-2 px-3';
      document.querySelector('#eventModal .modal-body').prepend(seriesInfo);
    }

    seriesInfo.style.display = 'none';
    seriesInfo.innerHTML = '';

    const isSeriesLinked = !!(event.series || event.is_recurring_instance || event.is_moved_exception);
    
    if (isSeriesLinked) {
      document.getElementById('isRecurring').checked = true;
      document.getElementById('recurringOptions').style.display = 'none';
      
      const s = event.series;
      const recurrenceText = s?.recurrence_text || '';
      const originalDateTxt = event.original_occurrence_date ? 
        new Date(event.original_occurrence_date + 'T00:00').toLocaleDateString() : null;

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

      document.getElementById('detachFromSeriesBtn').onclick = () => this.detachFromSeries(event.id);
    } else {
      document.getElementById('isRecurring').checked = false;
      document.getElementById('recurringOptions').style.display = 'none';
    }
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

      await this.calendar.loadEvents();
      const seriesInfo = document.getElementById('seriesInfo');
      if (seriesInfo) seriesInfo.style.display = 'none';
      bootstrap.Modal.getInstance(document.getElementById('eventModal')).hide();
    } catch (e) {
      console.error(e);
      alert('Error detaching from series');
    }
  }

  async saveEvent() {
    const form = document.getElementById('eventForm');
    const isSeries = this.calendar.currentEditType === 'series';
    
    // Handle series mode field disabling
    const disabled = [];
    if (isSeries) {
      ['eventStart','eventEnd','allDay','isRecurring'].forEach(id => {
        const el = document.getElementById(id);
        if (el && el.hasAttribute('required')) {
          disabled.push(el);
          el.removeAttribute('required');
          el.disabled = true;
        }
      });
    }

    if (!form.checkValidity()) {
      form.reportValidity();
      this.restoreDisabledFields(disabled);
      return;
    }

    const eventId = document.getElementById('eventId').value || null;
    const data = this.buildEventData(isSeries);
    const { url, method } = this.getApiEndpoint(eventId, isSeries);

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

      await this.calendar.loadEvents();
      if (this.calendar.currentView === 'recurring') this.calendar.render();
      bootstrap.Modal.getInstance(document.getElementById('eventModal')).hide();
    } catch (e) {
      console.error(e);
      alert(`Error saving ${isSeries ? 'series' : 'event'}: ${e.message}`);
    } finally {
      this.restoreDisabledFields(disabled, isSeries);
      this.calendar.currentEditType = null;
    }
  }

  buildEventData(isSeries) {
    const data = {
      title: document.getElementById('eventTitle').value,
      location: document.getElementById('eventLocation').value,
      description: document.getElementById('eventDescription').value,
      layer: document.getElementById('eventLayer').value
    };

    if (!isSeries) {
      data.start = document.getElementById('eventStart').value;
      data.end = document.getElementById('eventEnd').value;
      data.all_day = document.getElementById('allDay').checked;
      data.is_recurring = document.getElementById('isRecurring').checked;

      if (data.is_recurring) {
        const endType = document.querySelector('input[name="recurrenceEnd"]:checked').value;
        data.recurrence_type = document.getElementById('recurrenceType').value;
        data.recurrence_interval = parseInt(document.getElementById('recurrenceInterval').value, 10);
        data.recurrence_end_type = endType;
        
        if (endType === 'count') {
          data.recurrence_end_count = parseInt(document.getElementById('endAfterCount').value, 10);
        }
        if (endType === 'date') {
          data.recurrence_end_date = document.getElementById('endOnDate').value;
        }
      }
    } else {
      const endType = document.querySelector('input[name="recurrenceEnd"]:checked').value;
      data.recurrence_type = document.getElementById('recurrenceType').value;
      data.recurrence_interval = parseInt(document.getElementById('recurrenceInterval').value, 10);
      data.recurrence_end_type = endType;
      
      if (endType === 'count') {
        data.recurrence_end_count = parseInt(document.getElementById('endAfterCount').value, 10);
      }
      if (endType === 'date') {
        data.recurrence_end_date = document.getElementById('endOnDate').value;
      }
    }

    return data;
  }

  getApiEndpoint(eventId, isSeries) {
    if (isSeries) {
      return {
        url: eventId ? `/api/recurring-patterns/${eventId}` : '/api/recurring-patterns',
        method: eventId ? 'PUT' : 'POST'
      };
    } else {
      return {
        url: eventId ? `/api/events/${eventId}` : '/api/events',
        method: eventId ? 'PUT' : 'POST'
      };
    }
  }

  restoreDisabledFields(disabled, isSeries = false) {
    if (isSeries) {
      ['eventStart','eventEnd','allDay','isRecurring'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.disabled = false;
      });
    }
    disabled.forEach(el => el.setAttribute('required',''));
  }

  async deleteEvent() {
    const eventId = document.getElementById('eventId').value;
    const editType = this.calendar.currentEditType || 'single';
    
    if (!eventId || !confirm('Are you sure you want to delete this event?')) {
      return;
    }

    try {
      const url = editType === 'series' ? 
        `/api/recurring-patterns/${eventId}` : 
        `/api/events/${eventId}`;

      const response = await fetch(url, { method: 'DELETE' });
      
      if (response.ok) {
        await this.calendar.loadEvents();
        if (this.calendar.currentView === 'recurring') {
          this.calendar.render();
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
        await this.calendar.loadEvents();
        if (this.calendar.currentView === 'recurring') {
          this.calendar.render();
        }
      } else {
        alert('Error deleting recurring event');
      }
    } catch (error) {
      console.error('Error deleting recurring event:', error);
      alert('Error deleting recurring event');
    }
  }

  async copyEvent() {
    if (!this.calendar.dragDrop.draggedEvent || !this.calendar.dragDrop.dropTarget) return;

    const originalEvent = this.calendar.events.find(e => e.id === this.calendar.dragDrop.draggedEvent.id);
    if (!originalEvent) return;

    const { newStart, newEnd } = this.calculateNewTimes(originalEvent);
    
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(copiedEvent)
      });

      if (response.ok) {
        await this.calendar.loadEvents();
        bootstrap.Modal.getInstance(document.getElementById('moveConfirmModal')).hide();
      } else {
        alert('Error copying event');
      }
    } catch (error) {
      console.error('Error copying event:', error);
      alert('Error copying event');
    }
  }

  async confirmMoveEvent() {
    if (!this.calendar.dragDrop.draggedEvent || !this.calendar.dragDrop.dropTarget) return;

    const event = this.calendar.events.find(e => e.id === this.calendar.dragDrop.draggedEvent.id);
    if (!event) return;

    if (event.is_recurring_instance) {
      await this.handleRecurringInstanceMove(event);
    } else {
      await this.handleRegularEventMove(event);
    }
  }

  async handleRecurringInstanceMove(event) {
    const { newStart, newEnd } = this.calculateNewTimes(event);

    try {
      // Create deletion exception for original date
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(deletionException)
      });

      // Create moved event
      const newEvent = {
        title: event.title,
        start: this.toLocalInput(newStart),
        end: this.toLocalInput(newEnd),
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newEvent)
      });

      if (response.ok) {
        await this.calendar.loadEvents();
        bootstrap.Modal.getInstance(document.getElementById('moveConfirmModal')).hide();
      } else {
        const errorData = await response.json();
        alert(`Error moving recurring event: ${errorData.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error moving recurring event:', error);
      alert('Error moving recurring event');
    }
  }

  async handleRegularEventMove(event) {
    const { newStart, newEnd } = this.calculateNewTimes(event);
    
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedEvent)
      });

      if (response.ok) {
        await this.calendar.loadEvents();
        bootstrap.Modal.getInstance(document.getElementById('moveConfirmModal')).hide();
      } else {
        const errorData = await response.json();
        alert(`Error moving event: ${errorData.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error moving event:', error);
      alert('Error moving event');
    }
  }

  calculateNewTimes(event) {
    const originalStart = new Date(event.start);
    const originalEnd = new Date(event.end);
    const duration = originalEnd.getTime() - originalStart.getTime();
    
    const newStart = new Date(this.calendar.dragDrop.dropTarget.date);
    if (this.calendar.dragDrop.dropTarget.hour !== null) {
      newStart.setHours(parseInt(this.calendar.dragDrop.dropTarget.hour), originalStart.getMinutes(), 0, 0);
    } else {
      newStart.setHours(originalStart.getHours(), originalStart.getMinutes(), 0, 0);
    }
    
    const newEnd = new Date(newStart.getTime() + duration);
    return { newStart, newEnd };
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
    this.calendar.currentEditType = null;

    // Show all form fields
    document.querySelector('#eventStart').closest('.row').style.display = 'block';
    document.querySelector('#allDay').closest('.mb-3').style.display = 'block';
    document.getElementById('isRecurring').closest('.mb-3').style.display = 'block';
  }

  formatDateTimeLocal(value) {
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
      return value;
    }
    return this.toLocalInput(new Date(value));
  }

  toLocalInput(d) {
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
}