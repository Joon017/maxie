// layer-manager.js - Layer Management Module
class LayerManager {
  constructor(calendar) {
    this.calendar = calendar;
  }

  bindLayerHandlers() {
    // Layer form handlers
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

  renderLayersControls() {
    const layersList = document.getElementById('layersList');
    layersList.innerHTML = '';

    this.calendar.layers.forEach(layer => {
      const layerItem = document.createElement('div');
      layerItem.className = 'layer-item';
      layerItem.innerHTML = `
        <input type="checkbox" class="form-check-input layer-checkbox" id="layer-${layer.id}" ${layer.visible ? 'checked' : ''}>
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

    this.calendar.layers.forEach(layer => {
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
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ visible })
      });

      if (response.ok) {
        // Update local state
        const layer = this.calendar.layers.find(l => l.id === layerId);
        if (layer) {
          layer.visible = visible;
        }
        // Reload events to apply filtering
        await this.calendar.loadEvents();
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
      const promises = this.calendar.layers.map(layer => 
        fetch(`/api/layers/${layer.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ visible })
        })
      );

      await Promise.all(promises);

      // Update local state
      this.calendar.layers.forEach(layer => {
        layer.visible = visible;
      });

      // Update UI
      this.renderLayersControls();
      await this.calendar.loadEvents();
    } catch (error) {
      console.error('Error toggling all layers:', error);
      alert('Error updating layers');
    }
  }

  editLayer(layerId) {
    const layer = this.calendar.layers.find(l => l.id === layerId);
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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(layerData)
        });
        if (!response.ok) throw new Error('Failed to update layer');
      } else {
        // Create new layer
        const response = await fetch('/api/layers', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(layerData)
        });
        if (!response.ok) throw new Error('Failed to create layer');
      }

      // Refresh layers and events
      await this.calendar.loadLayers();
      await this.calendar.loadEvents();
      bootstrap.Modal.getInstance(document.getElementById('layerModal')).hide();
    } catch (error) {
      console.error('Error saving layer:', error);
      alert('Error saving layer');
    }
  }

  showDeleteLayerModal(layerId) {
    const layer = this.calendar.layers.find(l => l.id === layerId);
    if (!layer) return;

    this.calendar.layerToDelete = layerId;

    // Check if layer has events
    const layerEvents = this.calendar.events.filter(event => event.layer === layerId);
    const hasEvents = layerEvents.length > 0;

    document.getElementById('deleteLayerText').textContent = `Are you sure you want to delete "${layer.name}"?`;

    const migrationSection = document.getElementById('layerEventsMigration');
    if (hasEvents) {
      migrationSection.style.display = 'block';
      
      // Populate migration layer dropdown
      const migrationSelect = document.getElementById('migrationLayer');
      migrationSelect.innerHTML = '';
      this.calendar.layers
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
    if (!this.calendar.layerToDelete) return;

    try {
      const migrationOption = document.querySelector('input[name="migrationOption"]:checked')?.value;
      const migrationLayer = document.getElementById('migrationLayer').value;

      const requestBody = {
        migration_option: migrationOption,
        migration_layer: migrationLayer
      };

      const response = await fetch(`/api/layers/${this.calendar.layerToDelete}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });

      if (!response.ok) throw new Error('Failed to delete layer');

      // Refresh layers and events
      await this.calendar.loadLayers();
      await this.calendar.loadEvents();
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
    this.calendar.layerToDelete = null;
    document.getElementById('moveEvents').checked = true;
    document.getElementById('layerEventsMigration').style.display = 'none';
  }
}