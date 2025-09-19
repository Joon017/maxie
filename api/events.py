# api/events.py - Events API Blueprint
from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid
from utils.data_manager import load_events, save_events, load_layers, load_recurring_patterns
from utils.recurring_utils import generate_instances_from_pattern, get_recurrence_text

events_bp = Blueprint('events', __name__)

def is_orphan_exception(event):
    """Check if event references a series that no longer exists"""
    patterns = load_recurring_patterns()
    pattern_id = event.get('pattern_id') or event.get('original_pattern_id')
    if not pattern_id:
        return False
    if pattern_id in patterns:
        return False
    
    # Treat any deletion/moved/instance as orphan exception if series is gone
    return bool(
        event.get('is_deletion_exception') or
        event.get('is_moved_exception') or
        event.get('is_recurring_instance')
    )

@events_bp.route('/events', methods=['GET'])
def get_events():
    """Get all events (regular events + generated recurring instances) with layer filtering"""
    events = load_events()
    patterns = load_recurring_patterns()
    layers = load_layers()

    # 1) Start with regular events, drop deletion markers and orphaned exceptions
    all_events = {}
    for event_id, event in events.items():
        if event.get('is_deletion_exception', False):
            continue  # never show deletion markers
        if is_orphan_exception(event):
            continue  # safety-net: hide orphaned exceptions
        all_events[event_id] = event

    # 2) Generate instances from recurring patterns
    for pattern in patterns.values():
        instances = generate_instances_from_pattern(pattern)
        for instance in instances:
            inst = instance.copy()
            inst['is_recurring_instance'] = True
            inst['is_moved_exception'] = bool(inst.get('is_moved_exception', False))
            inst['is_deletion_exception'] = False
            all_events[inst['id']] = inst

    # 3) Enrich with series info and normalize flags
    enriched_events = []
    for event in all_events.values():
        event_out = event.copy()

        # Normalize booleans
        event_out['is_recurring_instance'] = bool(event_out.get('is_recurring_instance', False))
        event_out['is_moved_exception'] = bool(event_out.get('is_moved_exception', False))
        event_out['is_deletion_exception'] = bool(event_out.get('is_deletion_exception', False))

        # Series enrichment
        pattern_id = event_out.get('pattern_id') or event_out.get('original_pattern_id')
        if pattern_id and pattern_id in patterns:
            pattern = patterns[pattern_id]
            event_out['series'] = {
                'id': pattern['id'],
                'title': pattern.get('title', ''),
                'first_occurrence': pattern.get('first_occurrence'),
                'start_time': pattern.get('start_time'),
                'recurrence_text': get_recurrence_text(pattern),
            }
            event_out['is_recurring_linked'] = True
        else:
            event_out['is_recurring_linked'] = False

        enriched_events.append(event_out)

    # 4) Filter by visible layers and attach layer metadata
    visible_layers = [layer_id for layer_id, layer in layers.items() if layer.get('visible', True)]
    filtered_events = []
    
    for event in enriched_events:
        layer_id = event.get('layer', 'personal')
        if layer_id in visible_layers:
            event_out = event.copy()
            if layer_id in layers:
                event_out['layer_color'] = layers[layer_id]['color']
                event_out['layer_name'] = layers[layer_id]['name']
            filtered_events.append(event_out)

    return jsonify(filtered_events)

@events_bp.route('/events', methods=['POST'])
def create_event():
    """Create a new event"""
    from api.recurring_patterns import create_recurring_pattern
    
    data = request.json
    
    if data.get('is_recurring', False):
        # Create recurring pattern instead of regular event
        return create_recurring_pattern()
    
    # Create regular event
    events = load_events()
    event_id = str(uuid.uuid4())
    
    event = {
        'id': event_id,
        'title': data.get('title', ''),
        'start': data.get('start', ''),
        'end': data.get('end', ''),
        'location': data.get('location', ''),
        'description': data.get('description', ''),
        'all_day': data.get('all_day', False),
        'layer': data.get('layer', 'personal'),
        'is_recurring_instance': False,
        # Exception metadata
        'is_deletion_exception': data.get('is_deletion_exception', False),
        'is_moved_exception': data.get('is_moved_exception', False),
        'original_pattern_id': data.get('original_pattern_id'),
        'original_occurrence_date': data.get('original_occurrence_date'),
        'created_at': datetime.now().isoformat()
    }
    
    events[event_id] = event
    
    if save_events(events):
        return jsonify(event), 201
    else:
        return jsonify({'error': 'Failed to save event'}), 500

@events_bp.route('/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    """Update an event"""
    events = load_events()
    if event_id not in events:
        return jsonify({'error': 'Event not found'}), 404

    data = request.json
    event = events[event_id]

    def provided(key):
        # Help distinguish between "not provided" and "provided as null/false"
        return key in data

    # Regular fields
    if provided('title'): event['title'] = data['title']
    if provided('start'): event['start'] = data['start']
    if provided('end'): event['end'] = data['end']
    if provided('location'): event['location'] = data['location']
    if provided('description'): event['description'] = data['description']
    if provided('all_day'): event['all_day'] = data['all_day']
    if provided('layer'): event['layer'] = data['layer']

    # Exception metadata (allow clearing)
    if provided('is_deletion_exception'): event['is_deletion_exception'] = data['is_deletion_exception']
    if provided('is_moved_exception'): event['is_moved_exception'] = data['is_moved_exception']
    if provided('original_pattern_id'): event['original_pattern_id'] = data['original_pattern_id']
    if provided('original_occurrence_date'): event['original_occurrence_date'] = data['original_occurrence_date']

    event['updated_at'] = datetime.now().isoformat()

    if save_events(events):
        return jsonify(event)
    return jsonify({'error': 'Failed to update event'}), 500

@events_bp.route('/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    """Delete an event"""
    from api.recurring_patterns import delete_recurring_pattern
    
    # Check if it's a recurring pattern
    patterns = load_recurring_patterns()
    if event_id in patterns:
        return delete_recurring_pattern(event_id)
    
    # Handle regular event
    events = load_events()
    if event_id not in events:
        return jsonify({'error': 'Event not found'}), 404
    
    del events[event_id]
    
    if save_events(events):
        return jsonify({'message': 'Event deleted'}), 200
    else:
        return jsonify({'error': 'Failed to delete event'}), 500