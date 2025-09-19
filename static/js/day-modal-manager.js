// day-modal-manager.js - Day Modal Management Module
class DayModalManager {
  constructor(calendar) {
    this.calendar = calendar;
    this.dayModalDate = null;
    this._dayModal = null;
    this._debounce = this.debounce.bind(this);
  }

  async openDayModal(date) {
    // Set the day the modal should show
    this.dayModalDate = (date instanceof Date) ? new Date(date) : new Date(`${date}T00:00`);

    // Ensure modal exists
    this.ensureDayModalShell();

    // Render the modal contents
    this.renderDayModal();

    // Wire sidebar components
    await this.setupDaySidebar();

    // Show the modal
    if (!this._dayModal) {
      this._dayModal = new bootstrap.Modal(document.getElementById('dayModal'));
    }
    this._dayModal.show();
  }

  ensureDayModalShell() {
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
              <div class="d-flex align-items-center gap-2">
                <button class="btn btn-sm btn-outline-secondary" id="dayZoomOut" title="Zoom out">-</button>
                <span class="small text-muted" id="dayZoomLabel">60%</span>
                <button class="btn btn-sm btn-outline-secondary" id="dayZoomIn" title="Zoom in">+</button>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
              </div>
            </div>
            <div class="modal-body day-modal-body p-0 d-flex" style="height:70vh;">
              <!-- Calendar section (left) -->
              <div class="day-calendar-container" style="flex: 1; overflow: hidden;">
                <div class="day-calendar-scroll" style="height: 100%; overflow-y: auto;">
                  <div class="d-flex" style="position:relative;">
                    <div class="day-modal-ruler" style="width:110px; border-right:1px solid var(--border-color);"></div>
                    <div class="day-modal-grid position-relative flex-grow-1"></div>
                  </div>
                </div>
              </div>
              <!-- Sidebar (right) -->
              <div class="day-sidebar" style="width: 300px; border-left: 1px solid var(--border-color); padding: 1rem; overflow-y: auto;">
                <!-- Tasks Section -->
                <div class="mb-4">
                  <div class="d-flex align-items-center justify-content-between mb-2">
                    <h6 class="mb-0">Tasks</h6>
                    <small class="text-muted" id="tasksDateLabel"></small>
                  </div>
                  <div class="input-group input-group-sm mb-2">
                    <input type="text" class="form-control" id="addTaskInput" placeholder="Add task...">
                    <button class="btn btn-outline-secondary" type="button" id="addTaskBtn">+</button>
                  </div>
                  <ul class="list-unstyled" id="tasksList"></ul>
                  <button class="btn btn-primary btn-sm w-100" id="openKanbanBtn">Open Board</button>
                </div>
                
                <!-- Notes Section -->
                <div>
                  <div class="d-flex align-items-center justify-content-between mb-2">
                    <h6 class="mb-0">Notes</h6>
                    <small class="text-muted" id="notesDateLabel"></small>
                  </div>
                  <textarea class="form-control" id="notesTextarea" rows="8" placeholder="Add notes for this day..."></textarea>
                </div>
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

    // Bind navigation buttons
    document.getElementById('dayModalPrev').addEventListener('click', () => {
      this.navigateDay(-1);
    });

    document.getElementById('dayModalNext').addEventListener('click', () => {
      this.navigateDay(1);
    });

    // Bind zoom controls
    document.getElementById('dayZoomOut').addEventListener('click', () => {
      this.calendar.setDayZoom(-0.2);
    });

    document.getElementById('dayZoomIn').addEventListener('click', () => {
      this.calendar.setDayZoom(0.2);
    });

    // Bind new event button
    document.getElementById('dayModalNewEvent').addEventListener('click', () => {
      const dateStr = this.calendar.toLocalYMD(this.dayModalDate);
      this.calendar.eventManager.newEvent(dateStr, 9); // Default to 9 AM
    });
  }

  navigateDay(direction) {
    if (!this.dayModalDate) return;
    
    this.dayModalDate.setDate(this.dayModalDate.getDate() + direction);
    this.renderDayModal();
    this.setupDaySidebar(); // Refresh sidebar for new date
  }

  renderDayModal() {
    const modalEl = document.getElementById('dayModal');
    const titleEl = modalEl.querySelector('.day-modal-title');
    const scrollEl = modalEl.querySelector('.day-calendar-scroll');
    const rulerEl = modalEl.querySelector('.day-modal-ruler');
    const gridEl = modalEl.querySelector('.day-modal-grid');

    // Zoom and sizing
    const PX_PER_MIN = this.calendar.dayZoom || 0.6;
    const DAY_MINUTES = 24 * 60;
    const HOUR_PX = 60 * PX_PER_MIN;

    // Update zoom label
    const zoomLabel = document.getElementById('dayZoomLabel');
    if (zoomLabel) {
      zoomLabel.textContent = `${Math.round(this.calendar.dayZoom * 100)}%`;
    }

    // Apply CSS custom property for background stripes
    gridEl.style.setProperty('--hourH', `${HOUR_PX}px`);
    gridEl.style.height = `${DAY_MINUTES * PX_PER_MIN}px`;

    // Header
    const d = this.dayModalDate || new Date();
    titleEl.textContent = d.toLocaleDateString(undefined, {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });

    // Build hour ruler
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

    // Clear and render events
    gridEl.innerHTML = '';
    this.renderDayEvents(gridEl, d, PX_PER_MIN);
  }

  renderDayEvents(gridEl, date, PX_PER_MIN) {
    const DAY_MINUTES = 24 * 60;
    const y = date.getFullYear(), m = date.getMonth(), day = date.getDate();
    const startOfDay = new Date(y, m, day, 0, 0, 0, 0);

    const minsFromMidnight = (dt) => 
      Math.max(0, Math.min(DAY_MINUTES, Math.round((dt - startOfDay) / 60000)));

    // Collect today's events with metadata
    const todays = this.calendar.getEventsForDay(date).map(ev => {
      const s = new Date(ev.start);
      const e = new Date(ev.end);
      const startMin = minsFromMidnight(s);
      const endMin = Math.max(startMin + 15, minsFromMidnight(e)); // min 15m duration
      return { ev, s, e, startMin, endMin, col: 0, cols: 1 };
    });

    // Sort for grouping
    todays.sort((a, b) => a.startMin - b.startMin || a.endMin - b.endMin);

    // Group overlapping events into clusters
    const groups = [];
    for (const item of todays) {
      let placed = false;
      for (const g of groups) {
        const overlaps = g.some(x => !(item.endMin <= x.startMin || x.endMin <= item.startMin));
        if (overlaps) {
          g.push(item);
          placed = true;
          break;
        }
      }
      if (!placed) groups.push([item]);
    }

    // Assign columns per group (greedy algorithm)
    for (const group of groups) {
      const activeEnds = []; // end minute per column, or null if free
      for (const item of group) {
        // Free up columns that have ended
        for (let c = 0; c < activeEnds.length; c++) {
          if (activeEnds[c] !== null && activeEnds[c] <= item.startMin) {
            activeEnds[c] = null;
          }
        }
        
        // Find first available column
        let colIdx = activeEnds.findIndex(v => v === null);
        if (colIdx === -1) {
          colIdx = activeEnds.length;
          activeEnds.push(null);
        }
        
        item.col = colIdx;
        activeEnds[colIdx] = item.endMin;
      }
      
      const totalCols = Math.max(1, activeEnds.length);
      group.forEach(it => it.cols = totalCols);
    }

    // Render events with pixel-accurate positioning
    const GAP_PX = 6;
    const PAD_L = 8;
    const PAD_R = 8;
    const gridRect = gridEl.getBoundingClientRect();
    const innerWidth = Math.max(0, gridRect.width - PAD_L - PAD_R);
    let firstTopPx = null;

    groups.flat().forEach(item => {
      const { ev, s, e, startMin, endMin, col, cols } = item;
      const totalGap = (cols - 1) * GAP_PX;
      const colWidth = Math.max(40, (innerWidth - totalGap) / cols);
      const leftPx = PAD_L + col * (colWidth + GAP_PX);
      const topPx = startMin * PX_PER_MIN;
      const heightPx = Math.max(15 * PX_PER_MIN, (endMin - startMin) * PX_PER_MIN);

      const node = document.createElement('div');
      node.className = 'day-modal-event';
      node.style.top = `${topPx}px`;
      node.style.height = `${heightPx}px`;
      node.style.left = `${leftPx}px`;
      node.style.width = `${colWidth}px`;
      node.style.backgroundColor = ev.layer_color || '#28a745';
      node.setAttribute('data-event-id', ev.id);

      const badge = ev.is_recurring_linked ? '<span class="recurring-indicator"></span>' : '';
      const moved = ev.is_moved_exception ? '<span class="recurring-indicator moved" title="Moved from series"></span>' : '';
      
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

      node.addEventListener('click', () => this.calendar.eventManager.editEvent(ev.id));
      gridEl.appendChild(node);

      if (firstTopPx === null) firstTopPx = topPx;
    });

    // Scroll to first event (or 8am if none)
    const target = (firstTopPx ?? (8 * 60 * PX_PER_MIN)) - 40;
    const scrollEl = document.querySelector('.day-calendar-scroll');
    if (scrollEl) {
      scrollEl.scrollTop = Math.max(0, target);
    }
  }

  async setupDaySidebar() {
    const ymd = this.calendar.toLocalYMD(this.dayModalDate || new Date());
    
    // Update labels
    const opts = { weekday:'long', year:'numeric', month:'long', day:'numeric' };
    const label = (this.dayModalDate || new Date()).toLocaleDateString(undefined, opts);
    
    const tasksDateLabel = document.getElementById('tasksDateLabel');
    const notesDateLabel = document.getElementById('notesDateLabel');
    if (tasksDateLabel) tasksDateLabel.textContent = label;
    if (notesDateLabel) notesDateLabel.textContent = label;

    // Setup tasks
    await this.calendar.taskManager.loadTasks();
    this.calendar.taskManager.renderDayTasks(ymd);

    // Wire task input
    const addInput = document.getElementById('addTaskInput');
    const addBtn = document.getElementById('addTaskBtn');
    if (addBtn) {
      addBtn.onclick = () => this.calendar.taskManager.addTaskFromSidebar(ymd);
    }
    if (addInput) {
      addInput.onkeydown = (e) => {
        if (e.key === 'Enter') this.calendar.taskManager.addTaskFromSidebar(ymd);
      };
    }

    // Open Kanban board
    const kbBtn = document.getElementById('openKanbanBtn');
    if (kbBtn) {
      kbBtn.onclick = () => this.calendar.taskManager.openKanbanModal(ymd);
    }

    // Setup notes
    this.setupNotes(ymd);
  }

  setupNotes(ymd) {
    const notesArea = document.getElementById('notesTextarea');
    if (!notesArea) return;

    notesArea.value = this.loadNotes(ymd);
    notesArea.oninput = this._debounce(() => {
      this.saveNotes(ymd, notesArea.value);
    }, 300);
  }

  // Notes storage helpers
  loadNotes(ymd) {
    return localStorage.getItem(`notes:${ymd}`) || '';
  }

  saveNotes(ymd, text) {
    localStorage.setItem(`notes:${ymd}`, text);
  }

  // Utility methods
  debounce(fn, ms = 300) {
    let timeout;
    return (...args) => {
      clearTimeout(timeout);
      timeout = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  setDayZoom(delta) {
    // Clamp zoom between 0.4 (24px/hour) and 1.2 (72px/hour)
    this.calendar.dayZoom = Math.min(1.2, Math.max(0.4, this.calendar.dayZoom + delta));
    this.renderDayModal();
  }
}