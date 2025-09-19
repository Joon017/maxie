// drag-drop-handler.js - Drag and Drop Module
class DragDropHandler {
  constructor(calendar) {
    this.calendar = calendar;
    this.draggedEvent = null;
    this.dropTarget = null;
  }

  bindDragEvents(eventElement) {
    eventElement.addEventListener('dragstart', this.handleDragStart.bind(this));
    eventElement.addEventListener('dragend', this.handleDragEnd.bind(this));
    
    // Prevent default click behavior when dragging
    eventElement.addEventListener('click', (e) => {
      if (this.draggedEvent && this.draggedEvent.isDragging) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  }

  bindDropEvents(dropZone) {
    dropZone.addEventListener('dragover', this.handleDragOver.bind(this));
    dropZone.addEventListener('drop', this.handleDrop.bind(this));
    dropZone.addEventListener('dragenter', this.handleDragEnter.bind(this));
    dropZone.addEventListener('dragleave', this.handleDragLeave.bind(this));
  }

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

    // Get drop zone data
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
    const event = this.calendar.events.find(e => e.id === this.draggedEvent.id);
    if (!event || !this.dropTarget) return;

    const originalDate = new Date(event.start);
    const originalDateStr = originalDate.toLocaleDateString();
    const originalTimeStr = originalDate.toLocaleTimeString([], {
      hour: '2-digit', 
      minute: '2-digit'
    });

    const newDate = new Date(this.dropTarget.date);
    if (this.dropTarget.hour !== null) {
      newDate.setHours(parseInt(this.dropTarget.hour), 0, 0, 0);
    }
    
    const newDateStr = newDate.toLocaleDateString();
    const newTimeStr = newDate.toLocaleTimeString([], {
      hour: '2-digit', 
      minute: '2-digit'
    });

    const confirmText = `Move "${event.title}" from ${originalDateStr} ${originalTimeStr} to ${newDateStr} ${newTimeStr}?`;
    document.getElementById('moveConfirmText').textContent = confirmText;

    const modal = new bootstrap.Modal(document.getElementById('moveConfirmModal'));
    modal.show();
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
}