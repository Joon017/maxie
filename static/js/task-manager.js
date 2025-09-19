// task-manager.js - Task Management Module
class TaskManager {
  constructor(calendar) {
    this.calendar = calendar;
    this.tasks = [];
    this._taskModal = null;
    this._taskSaveWired = false;
    this.kanbanZoom = 1;
  }

  // API helpers with localStorage fallback
  async loadTasks(date = null) {
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
    try {
      const res = await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) throw new Error('createTask failed');
      
      const created = await res.json();
      this.tasks.push(created);
      return created;
    } catch (error) {
      // Fallback to local storage
      const newTask = {
        ...payload,
        id: payload.id || String(Date.now()),
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      this.tasks.push(newTask);
      this.saveTasksLocally();
      return newTask;
    }
  }

  async updateTask(id, patch) {
    try {
      const res = await fetch(`/api/tasks/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch)
      });
      
      if (!res.ok) throw new Error('updateTask failed');
      
      const updated = await res.json();
      const i = this.tasks.findIndex(t => t.id === id);
      if (i !== -1) this.tasks[i] = updated;
      return updated;
    } catch (error) {
      // Fallback to local storage
      const i = this.tasks.findIndex(t => t.id === id);
      if (i !== -1) {
        this.tasks[i] = { ...this.tasks[i], ...patch, updated_at: new Date().toISOString() };
        this.saveTasksLocally();
        return this.tasks[i];
      }
      throw error;
    }
  }

  async deleteTask(id) {
    try {
      const res = await fetch(`/api/tasks/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error();
    } catch {
      // Ignore API errors, proceed with local deletion
    }
    
    this.tasks = this.tasks.filter(t => t.id !== id);
    this.saveTasksLocally();
  }

  // Utility methods
  getTasksForDate(ymd) {
    return this.tasks.filter(t => t.date === ymd);
  }

  // Kanban Modal Management
  async openKanbanModal(ymd) {
    const dateStr = ymd || (this.calendar.dayModalDate ? 
      this.calendar.toLocalYMD(this.calendar.dayModalDate) : 
      this.calendar.toLocalYMD(new Date()));

    // Hide day modal if open
    const dayEl = document.getElementById('dayModal');
    const dayInst = dayEl ? bootstrap.Modal.getInstance(dayEl) : null;
    if (dayInst) dayInst.hide();

    // Prepare Kanban modal
    const kbEl = document.getElementById('kanbanModal');
    kbEl.dataset.ymd = dateStr;
    document.getElementById('kanbanTitle').textContent = `Tasks Board — ${dateStr}`;

    const kbModal = this.getOrCreateModal(kbEl);

    // Restore day modal when Kanban closes
    const onHidden = () => {
      kbEl.removeEventListener('hidden.bs.modal', onHidden);
      if (dayInst) dayInst.show();
    };
    kbEl.addEventListener('hidden.bs.modal', onHidden);

    // Wire actions
    this.wireKanbanActions(dateStr);
    this.setupZoomControls();

    // Fetch tasks and render
    await this.loadTasks();
    this.renderKanban(dateStr);

    kbModal.show();
  }

  wireKanbanActions(dateStr) {
    // New Task button
    const kbNewTaskBtn = document.getElementById('kbNewTaskBtn');
    if (kbNewTaskBtn) {
      kbNewTaskBtn.onclick = () => this.openTaskModal({ ymd: dateStr });
    }

    // Quick Add button
    const addBtn = document.getElementById('kbAdd');
    if (addBtn) {
      addBtn.onclick = () => {
        const title = (document.getElementById('kbTitle')?.value || '').trim();
        const details = (document.getElementById('kbDetails')?.value || '').trim();
        const when = (document.getElementById('kbWhen')?.value || '').trim();
        const status = (document.getElementById('kbStatus')?.value || 'Planned');

        this.openTaskModal({
          ymd: dateStr,
          task: {
            id: null,
            title,
            details,
            status: status.toLowerCase().replace(' ', '_'),
            due_at: when ? new Date(when).toISOString() : null
          }
        });
      };
    }
  }

  setupZoomControls() {
    const zoomOut = document.getElementById('kanbanZoomOut');
    const zoomIn = document.getElementById('kanbanZoomIn');
    const zoomLbl = document.getElementById('kanbanZoomLabel');
    const board = document.getElementById('kanbanBoard');

    const applyZoom = () => {
      board.style.zoom = this.kanbanZoom;
      zoomLbl.textContent = `${Math.round(this.kanbanZoom * 100)}%`;
    };

    if (zoomOut) zoomOut.onclick = () => {
      this.kanbanZoom = Math.max(0.7, this.kanbanZoom - 0.1);
      applyZoom();
    };

    if (zoomIn) zoomIn.onclick = () => {
      this.kanbanZoom = Math.min(1.5, this.kanbanZoom + 0.1);
      applyZoom();
    };

    applyZoom();
  }

  renderKanban(ymd) {
    // Partition tasks by status
    const by = {
      planned: [],
      started: [],
      in_progress: [],
      completed: []
    };

    this.getTasksForDate(ymd).forEach(t => {
      const k = (t.status || 'planned');
      (by[k] || by.planned).push(t);
    });

    // Update counts
    this.updateStatusCounts(by);

    // Render each column
    this.mountColumn('kbPlanned', by.planned, 'planned', ymd);
    this.mountColumn('kbStarted', by.started, 'started', ymd);
    this.mountColumn('kbProgress', by.in_progress, 'in_progress', ymd);
    this.mountColumn('kbDone', by.completed, 'completed', ymd);
  }

  updateStatusCounts(by) {
    const setTxt = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.textContent = String(v);
    };

    setTxt('kbCntPlanned', by.planned.length);
    setTxt('kbCntStarted', by.started.length);
    setTxt('kbCntProgress', by.in_progress.length);
    setTxt('kbCntDone', by.completed.length);
  }

  mountColumn(bodyId, items, status, ymd) {
    const body = document.getElementById(bodyId);
    if (!body) return;

    body.innerHTML = items.map(t => this.cardHTML(t)).join('');

    // Bind drag events
    body.querySelectorAll('.kb-card').forEach(card => {
      card.addEventListener('dragstart', (e) => {
        e.dataTransfer.setData('text/plain', card.dataset.id || '');
      });
    });

    // Bind edit/delete events
    body.querySelectorAll('.kb-edit').forEach(btn => {
      btn.onclick = () => {
        const t = this.tasks.find(x => x.id === btn.dataset.id);
        if (t) this.openTaskModal({ ymd, task: t });
      };
    });

    body.querySelectorAll('.kb-del').forEach(btn => {
      btn.onclick = async () => {
        const t = this.tasks.find(x => x.id === btn.dataset.id);
        if (!t || !confirm('Delete this task?')) return;
        
        await this.deleteTask(t.id);
        this.renderKanban(ymd);
        if (this.calendar.dayModalDate) {
          this.renderDayTasks(this.calendar.toLocalYMD(this.calendar.dayModalDate));
        }
      };
    });

    // Set up drop target
    this.setupDropTarget(body, status, ymd);
  }

  setupDropTarget(body, newStatus, ymd) {
    const col = body.closest('.kb-col');
    
    body.ondragover = (e) => {
      e.preventDefault();
      col?.classList.add('drag-over');
    };

    body.ondragleave = () => {
      col?.classList.remove('drag-over');
    };

    body.ondrop = async (e) => {
      e.preventDefault();
      col?.classList.remove('drag-over');
      
      const id = e.dataTransfer.getData('text/plain');
      if (!id || !newStatus) return;

      const task = this.tasks.find(x => x.id === id);
      if (!task || task.status === newStatus) return;

      if (!confirm(`Move "${task.title}" to ${newStatus.replace('_', ' ')}?`)) return;

      await this.updateTask(id, {
        status: newStatus,
        updated_at: new Date().toISOString()
      });

      this.renderKanban(ymd);
      if (this.calendar.dayModalDate) {
        this.renderDayTasks(this.calendar.toLocalYMD(this.calendar.dayModalDate));
      }
    };
  }

  cardHTML(t) {
    return `
      <div class="kb-card" draggable="true" data-id="${t.id}">
        <div class="kb-card-title">${this.calendar.escapeHtml(t.title || '(untitled)')}</div>
        <div class="kb-card-meta">
          ${t.due_at ? `Due: ${new Date(t.due_at).toLocaleString()}` : ''}
        </div>
        <div class="kb-card-actions mt-1">
          <button class="btn btn-sm btn-outline-secondary kb-edit" data-id="${t.id}">Edit</button>
          <button class="btn btn-sm btn-outline-danger kb-del" data-id="${t.id}">Delete</button>
        </div>
      </div>
    `;
  }

  // Task Modal Management
  openTaskModal({ ymd, task = null }) {
    const modalEl = document.getElementById('taskEditModal');
    if (!this._taskModal) this._taskModal = new bootstrap.Modal(modalEl);

    // Get form elements
    const idEl = modalEl.querySelector('#taskId');
    const nameEl = modalEl.querySelector('#taskName');
    const dueEl = modalEl.querySelector('#taskDueAt');
    const detEl = modalEl.querySelector('#taskDetails');
    const stEl = modalEl.querySelector('#taskStatus');
    const comEl = modalEl.querySelector('#taskCommittedAt');
    const delBtn = modalEl.querySelector('#taskDeleteBtn');
    const title = modalEl.querySelector('#taskEditTitle');

    if (task && task.id) {
      // Edit existing task
      idEl.value = task.id;
      nameEl.value = task.title || '';
      dueEl.value = task.due_at ? task.due_at.slice(0, 16) : '';
      detEl.value = task.details || '';
      stEl.value = task.status || 'planned';
      comEl.value = task.committed_at ? new Date(task.committed_at).toLocaleString() : '';
      delBtn.classList.remove('d-none');
      title.textContent = 'Edit Task';

      delBtn.onclick = async () => {
        if (!confirm('Delete this task?')) return;
        await this.deleteTask(task.id);
        this._taskModal.hide();
        
        // Refresh UI
        const kEl = document.getElementById('kanbanModal');
        const kYmd = kEl?.dataset.ymd;
        if (kYmd) this.renderKanban(kYmd);
        if (this.calendar.dayModalDate) {
          this.renderDayTasks(this.calendar.toLocalYMD(this.calendar.dayModalDate));
        }
      };
    } else {
      // New task (or prefilled draft)
      idEl.value = '';
      nameEl.value = task?.title || '';
      dueEl.value = task?.due_at ? task.due_at.slice(0, 16) : '';
      detEl.value = task?.details || '';
      stEl.value = task?.status || 'planned';
      comEl.value = new Date().toLocaleString();
      delBtn.classList.add('d-none');
      title.textContent = 'New Task';
    }

    // Wire save handler once
    if (!this._taskSaveWired) {
      modalEl.querySelector('#taskEditForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.saveTaskFromModal();
      });
      this._taskSaveWired = true;
    }

    // Remember context for refreshing UI
    modalEl.dataset.ymd = ymd || 
      (document.getElementById('kanbanModal')?.dataset.ymd) || 
      this.calendar.toLocalYMD(new Date());

    this._taskModal.show();
  }

  async saveTaskFromModal() {
    const modalEl = document.getElementById('taskEditModal');
    const id = modalEl.querySelector('#taskId').value || null;
    const ymd = modalEl.dataset.ymd;

    const body = {
      title: modalEl.querySelector('#taskName').value.trim(),
      details: modalEl.querySelector('#taskDetails').value.trim(),
      due_at: modalEl.querySelector('#taskDueAt').value ? 
        new Date(modalEl.querySelector('#taskDueAt').value).toISOString() : null,
      status: modalEl.querySelector('#taskStatus').value || 'planned',
      date: ymd,
    };

    if (!body.title) {
      alert('Task name is required');
      return;
    }

    if (id) {
      await this.updateTask(id, { ...body, updated_at: new Date().toISOString() });
    } else {
      await this.createTask({ ...body, committed_at: new Date().toISOString() });
    }

    this._taskModal.hide();

    // Refresh UI
    const kEl = document.getElementById('kanbanModal');
    const kYmd = kEl?.dataset.ymd || ymd;
    if (kYmd) this.renderKanban(kYmd);
    if (this.calendar.dayModalDate) {
      this.renderDayTasks(this.calendar.toLocalYMD(this.calendar.dayModalDate));
    }
  }

  // Day sidebar task management
  renderDayTasks(ymd) {
    const ul = document.getElementById('tasksList');
    if (!ul) return;

    const items = this.getTasksForDate(ymd)
      .sort((a, b) => (a.status || '').localeCompare(b.status || '') || 
                     (a.created_at || '').localeCompare(b.created_at || ''))
      .map(t => `
        <li class="d-flex align-items-center justify-content-between py-1">
          <div class="task-text">
            <span class="kb-pill me-1">${(t.status || 'planned').replace('_', ' ')}</span>
            ${t.title}
          </div>
          <button class="task-del btn btn-sm btn-link text-danger p-0" data-task-id="${t.id}">&times;</button>
        </li>
      `);

    ul.innerHTML = items.join('') || '<div class="text-muted small">No tasks yet.</div>';

    ul.querySelectorAll('.task-del').forEach(btn => {
      btn.onclick = async () => {
        await this.deleteTask(btn.dataset.taskId);
        this.renderDayTasks(ymd);
      };
    });
  }

  async addTaskFromSidebar(ymd) {
    const input = document.getElementById('addTaskInput');
    const title = (input.value || '').trim();
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

  getOrCreateModal(el) {
    return bootstrap.Modal.getInstance(el) || new bootstrap.Modal(el);
  }
}