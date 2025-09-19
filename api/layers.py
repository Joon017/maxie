# api/layers.py - Layers API Blueprint
from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid
from utils.data_manager import load_layers, save_layers, load_events, save_events, load_recurring_patterns, save_recurring_patterns

layers_bp = Blueprint('layers', __name__)

@layers_bp.route('/layers', methods=['GET'])
def get_layers():
    """Get all layers"""
    layers = load_layers()
    return jsonify(list(layers.values()))

@layers_bp.route('/layers', methods=['POST'])
def create_layer():
    """Create a new layer"""
    layers = load_layers()
    data = request.json
    
    # Generate unique ID
    layer_id = str(uuid.uuid4())
    
    # Validate required fields
    if not data.get('name') or not data.get('color'):
        return jsonify({'error': 'Name and color are required'}), 400
    
    # Check for duplicate names
    existing_names = [layer['name'].lower() for layer in layers.values()]
    if data['name'].lower() in existing_names:
        return jsonify({'error': 'Layer name already exists'}), 400
    
    new_layer = {
        'id': layer_id,
        'name': data['name'],
        'color': data['color'],
        'visible': data.get('visible', True),
        'created_at': datetime.now().isoformat()
    }
    
    layers[layer_id] = new_layer
    
    if save_layers(layers):
        return jsonify(new_layer), 201
    else:
        return jsonify({'error': 'Failed to save layer'}), 500

@layers_bp.route('/layers/<layer_id>', methods=['PUT'])
def update_layer(layer_id):
    """Update a layer (visibility, name, color)"""
    layers = load_layers()
    if layer_id not in layers:
        return jsonify({'error': 'Layer not found'}), 404
    
    data = request.json
    layer = layers[layer_id]
    
    # Update allowed fields
    if 'visible' in data:
        layer['visible'] = data['visible']
    if 'name' in data:
        # Check for duplicate names (excluding current layer)
        existing_names = [l['name'].lower() for lid, l in layers.items() if lid != layer_id]
        if data['name'].lower() in existing_names:
            return jsonify({'error': 'Layer name already exists'}), 400
        layer['name'] = data['name']
    if 'color' in data:
        layer['color'] = data['color']
    
    layer['updated_at'] = datetime.now().isoformat()
    
    if save_layers(layers):
        return jsonify(layer)
    else:
        return jsonify({'error': 'Failed to update layer'}), 500

@layers_bp.route('/layers/<layer_id>', methods=['DELETE'])
def delete_layer(layer_id):
    """Delete a layer and handle event migration"""
    layers = load_layers()
    events = load_events()
    patterns = load_recurring_patterns()
    
    if layer_id not in layers:
        return jsonify({'error': 'Layer not found'}), 404
    
    # Prevent deleting the last layer
    if len(layers) <= 1:
        return jsonify({'error': 'Cannot delete the last layer'}), 400
    
    data = request.json or {}
    migration_option = data.get('migration_option', 'move')
    migration_layer = data.get('migration_layer', 'personal')
    
    # Find events and patterns in this layer
    layer_events = [event for event in events.values() if event.get('layer') == layer_id]
    layer_patterns = [pattern for pattern in patterns.values() if pattern.get('layer') == layer_id]
    
    if layer_events or layer_patterns:
        if migration_option == 'move':
            # Move events and patterns to another layer
            if migration_layer not in layers:
                return jsonify({'error': 'Migration layer not found'}), 400
            
            for event in layer_events:
                event['layer'] = migration_layer
                event['updated_at'] = datetime.now().isoformat()
            
            for pattern in layer_patterns:
                pattern['layer'] = migration_layer
                pattern['updated_at'] = datetime.now().isoformat()
                
        elif migration_option == 'delete':
            # Delete all events and patterns in this layer
            events_to_delete = [event['id'] for event in layer_events]
            for event_id in events_to_delete:
                del events[event_id]
            
            patterns_to_delete = [pattern['id'] for pattern in layer_patterns]
            for pattern_id in patterns_to_delete:
                del patterns[pattern_id]
    
    # Delete the layer
    del layers[layer_id]
    
    # Save all files
    if save_layers(layers) and save_events(events) and save_recurring_patterns(patterns):
        return jsonify({'message': 'Layer deleted successfully'}), 200
    else:
        return jsonify({'error': 'Failed to delete layer'}), 500