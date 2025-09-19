# api/recurring_patterns.py - Recurring Patterns API Blueprint
from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid
from utils.data_manager import (
    load_recurring_patterns, save_recurring_patterns, 
    load_layers, load_events, save_events
)
from utils.recurring_utils import get_recurrence_text

patterns_bp = Blueprint('recurring_patterns', __name__)

@patterns_bp.route('/recurring-patterns', methods=['GET'])
def get_recurring_patterns():
    """Get all recurring patterns with layer info and exceptions"""
    patterns = load_recurring_patterns()
    layers = load_layers()
    events = load_events()

    pattern_list = []
    for pattern in patterns.values():
        pattern_copy = pattern.copy()

        # Add layer metadata
        layer_id = pattern.get('layer', 'personal')
        if layer_id in layers:
            pattern_copy['layer_color'] = layers[layer_id]['color']
            pattern_copy['layer_name'] = layers[layer_id]['name']

        # Build exceptions for this pattern
        pattern_id = pattern['id']
        deletion_exceptions = []
        moved_exceptions = []

        for event in events.values():
            if event.get('is_deletion_exception') and event.get('original_pattern_id') == pattern_id:
                deletion_exceptions.append({
                    'id': event['id'],
                    'original_occurrence_date': event.get('original_occurrence_date'),
                })
            if event.get('is_moved_exception') and event.get('original_pattern_id') == pattern_id:
                moved_exceptions.append({
                    'id': event['id'],
                    'original_occurrence_date': event.get('original_occurrence_date'),
                    'new_start': event.get('start'),
                    'new_end': event.get('end'),
                    'title': event.get('title', pattern.get('title', '')),
                    'layer': event.get('layer', layer_id),
                })

        pattern_copy['exceptions'] = {
            'deletions': deletion_exceptions,
            'moves': moved_exceptions,
            'counts': {
                'deletions': len(deletion_exceptions),
                'moves': len(moved_exceptions),
                'total': len(deletion_exceptions) + len(moved_exceptions),
            }
        }

        pattern_list.append(pattern_copy)

    return jsonify(pattern_list)

@patterns_bp.route('/recurring-patterns/<pattern_id>', methods=['GET'])
def get_recurring_pattern(pattern_id):
    """Get a specific recurring pattern"""
    patterns = load_recurring_patterns()
    if pattern_id not in patterns:
        return jsonify({'error': 'Pattern not found'}), 404
    return jsonify(patterns[pattern_id])

@patterns_bp.route('/recurring-patterns', methods=['POST'])
def create_recurring_pattern():
    """Create a new recurring pattern"""
    patterns = load_recurring_patterns()
    data = request.json
    
    pattern_id = str(uuid.uuid4())
    
    # Parse the start datetime to extract date and time components
    start_datetime = datetime.fromisoformat(data.get('start', ''))
    end_datetime = datetime.fromisoformat(data.get('end', ''))
    
    pattern = {
        'id': pattern_id,
        'title': data.get('title', ''),
        'first_occurrence': start_datetime.date().isoformat(),
        'start_time': start_datetime.time().strftime('%H:%M'),
        'end_time': end_datetime.time().strftime('%H:%M'),
        'location': data.get('location', ''),
        'description': data.get('description', ''),
        'all_day': data.get('all_day', False),
        'layer': data.get('layer', 'personal'),
        'recurrence_type': data.get('recurrence_type', 'weekly'),
        'recurrence_interval': data.get('recurrence_interval', 1),
        'recurrence_end_type': data.get('recurrence_end_type', 'never'),
        'recurrence_end_date': data.get('recurrence_end_date'),
        'recurrence_end_count': data.get('recurrence_end_count', 10),
        'created_at': datetime.now().isoformat()
    }
    
    patterns[pattern_id] = pattern
    
    if save_recurring_patterns(patterns):
        return jsonify(pattern), 201
    else:
        return jsonify({'error': 'Failed to save recurring pattern'}), 500

@patterns_bp.route('/recurring-patterns/<pattern_id>', methods=['PUT'])
def update_recurring_pattern(pattern_id):
    """Update a recurring pattern"""
    patterns = load_recurring_patterns()
    if pattern_id not in patterns:
        return jsonify({'error': 'Pattern not found'}), 404
    
    data = request.json
    pattern = patterns[pattern_id]
    
    # Update pattern fields
    if 'title' in data:
        pattern['title'] = data['title']
    if 'start' in data:
        start_datetime = datetime.fromisoformat(data['start'])
        pattern['first_occurrence'] = start_datetime.date().isoformat()
        pattern['start_time'] = start_datetime.time().strftime('%H:%M')
    if 'end' in data:
        end_datetime = datetime.fromisoformat(data['end'])
        pattern['end_time'] = end_datetime.time().strftime('%H:%M')
    if 'location' in data:
        pattern['location'] = data['location']
    if 'description' in data:
        pattern['description'] = data['description']
    if 'all_day' in data:
        pattern['all_day'] = data['all_day']
    if 'layer' in data:
        pattern['layer'] = data['layer']
    if 'recurrence_type' in data:
        pattern['recurrence_type'] = data['recurrence_type']
    if 'recurrence_interval' in data:
        pattern['recurrence_interval'] = data['recurrence_interval']
    if 'recurrence_end_type' in data:
        pattern['recurrence_end_type'] = data['recurrence_end_type']
    if 'recurrence_end_date' in data:
        pattern['recurrence_end_date'] = data['recurrence_end_date']
    if 'recurrence_end_count' in data:
        pattern['recurrence_end_count'] = data['recurrence_end_count']
    
    pattern['updated_at'] = datetime.now().isoformat()
    
    if save_recurring_patterns(patterns):
        return jsonify(pattern)
    else:
        return jsonify({'error': 'Failed to update pattern'}), 500

@patterns_bp.route('/recurring-patterns/<pattern_id>', methods=['DELETE'])
def delete_recurring_pattern(pattern_id):
    """Delete a recurring pattern and its associated exceptions"""
    patterns = load_recurring_patterns()
    events = load_events()

    if pattern_id not in patterns:
        return jsonify({'error': 'Pattern not found'}), 404
    
    # Remove the pattern itself
    del patterns[pattern_id]
    
    # Remove any exception events linked to this pattern
    events_to_delete = []
    for event_id, event in events.items():
        if event.get('original_pattern_id') == pattern_id:
            events_to_delete.append(event_id)

    for event_id in events_to_delete:
        del events[event_id]

    # Save both files
    pattern_saved = save_recurring_patterns(patterns)
    events_saved = save_events(events)
    
    if pattern_saved and events_saved:
        return jsonify({
            'message': 'Pattern deleted successfully',
            'deleted_pattern': pattern_id, 
            'deleted_exceptions': len(events_to_delete)
        }), 200
    else:
        return jsonify({'error': 'Failed to delete pattern'}), 500

# Legacy compatibility routes
@patterns_bp.route('/recurring-events', methods=['GET'])
def get_recurring_events():
    """Legacy route - redirects to recurring patterns"""
    return get_recurring_patterns()

@patterns_bp.route('/recurring/<pattern_id>', methods=['DELETE'])
def delete_recurring_event(pattern_id):
    """Legacy route for deleting recurring patterns"""
    return delete_recurring_pattern(pattern_id)