from flask import Flask, render_template, request, jsonify, redirect, url_for, abort
from datetime import datetime, timedelta, time
import json
import uuid
import os
import calendar

app = Flask(__name__)

# JSON file storage
EVENTS_FILE = 'data/events.json'
PATTERNS_FILE = 'data/recurring_patterns.json'
LAYERS_FILE = 'data/layers.json'
TASKS_FILE = 'data/tasks.json'

# Default layers
DEFAULT_LAYERS = {
    'personal': {
        'id': 'personal',
        'name': 'Personal',
        'color': '#28a745',
        'visible': True,
        'created_at': datetime.now().isoformat()
    },
    'work': {
        'id': 'work', 
        'name': 'Work',
        'color': '#007bff',
        'visible': True,
        'created_at': datetime.now().isoformat()
    },
    'clients': {
        'id': 'clients',
        'name': 'Clients',
        'color': '#fd7e14',
        'visible': True,
        'created_at': datetime.now().isoformat()
    },
    'health': {
        'id': 'health',
        'name': 'Health & Fitness',
        'color': '#e83e8c',
        'visible': True,
        'created_at': datetime.now().isoformat()
    }
}

def ensure_data_directory():
    """Ensure the data directory exists"""
    os.makedirs('data', exist_ok=True)

def load_events():
    """Load event instances from JSON file"""
    ensure_data_directory()
    try:
        if os.path.exists(EVENTS_FILE):
            with open(EVENTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading events: {e}")
        return {}

def save_events(events_dict):
    """Save event instances to JSON file"""
    ensure_data_directory()
    try:
        with open(EVENTS_FILE, 'w') as f:
            json.dump(events_dict, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving events: {e}")
        return False

def load_recurring_patterns():
    """Load recurring patterns from JSON file"""
    ensure_data_directory()
    try:
        if os.path.exists(PATTERNS_FILE):
            with open(PATTERNS_FILE, 'r') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"Error loading recurring patterns: {e}")
        return {}

def save_recurring_patterns(patterns_dict):
    """Save recurring patterns to JSON file"""
    ensure_data_directory()
    try:
        with open(PATTERNS_FILE, 'w') as f:
            json.dump(patterns_dict, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving recurring patterns: {e}")
        return False

def load_layers():
    """Load layers from JSON file"""
    ensure_data_directory()
    try:
        if os.path.exists(LAYERS_FILE):
            with open(LAYERS_FILE, 'r') as f:
                return json.load(f)
        else:
            # Initialize with default layers
            save_layers(DEFAULT_LAYERS)
            return DEFAULT_LAYERS.copy()
    except Exception as e:
        print(f"Error loading layers: {e}")
        return DEFAULT_LAYERS.copy()

def save_layers(layers_dict):
    """Save layers to JSON file"""
    ensure_data_directory()
    try:
        with open(LAYERS_FILE, 'w') as f:
            json.dump(layers_dict, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving layers: {e}")
        return False
    
def load_tasks():
    ensure_data_directory()
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_tasks(tasks_dict):
    ensure_data_directory()
    with open(TASKS_FILE, 'w') as f:
        json.dump(tasks_dict, f, indent=2)
    return True

def generate_instances_from_pattern(pattern, max_occurrences=52):
    """Generate event instances from a recurring pattern, excluding exceptions"""
    instances = []
    
    # Get any exceptions for this pattern
    events = load_events()
    exceptions = [
        event for event in events.values() 
        if event.get('original_pattern_id') == pattern['id']
    ]
    exception_dates = [event.get('original_occurrence_date') for event in exceptions if event.get('original_occurrence_date')]
    
    print(f"Pattern {pattern['id']} has exception dates: {exception_dates}")  # Debug line
    
    # Parse pattern data
    recurrence_type = pattern.get('recurrence_type', 'weekly')
    recurrence_interval = pattern.get('recurrence_interval', 1)
    recurrence_end_type = pattern.get('recurrence_end_type', 'never')
    recurrence_end_date = pattern.get('recurrence_end_date')
    recurrence_end_count = pattern.get('recurrence_end_count', max_occurrences)
    
    # Parse first occurrence and time
    try:
        first_occurrence = datetime.strptime(pattern['first_occurrence'], '%Y-%m-%d').date()
        start_time = datetime.strptime(pattern['start_time'], '%H:%M').time()
        end_time = datetime.strptime(pattern['end_time'], '%H:%M').time()
    except (ValueError, KeyError) as e:
        print(f"Error parsing pattern times: {e}")
        return []
    
    # Calculate end conditions
    if recurrence_end_type == 'date' and recurrence_end_date:
        try:
            max_end_date = datetime.strptime(recurrence_end_date, '%Y-%m-%d').date()
        except ValueError:
            max_end_date = first_occurrence + timedelta(days=365)
    else:
        max_end_date = first_occurrence + timedelta(days=365)
    
    if recurrence_end_type == 'count':
        max_occurrences = recurrence_end_count
    
    current_date = first_occurrence
    count = 0
    
    while count < max_occurrences and current_date <= max_end_date:
        current_date_str = current_date.isoformat()
        
        # Skip this occurrence if there's an exception for this date
        if current_date_str in exception_dates:
            print(f"Skipping {current_date_str} due to exception")  # Debug line
            # Calculate next occurrence and continue without incrementing count
            try:
                if recurrence_type == 'daily':
                    current_date += timedelta(days=recurrence_interval)
                elif recurrence_type == 'weekly':
                    current_date += timedelta(weeks=recurrence_interval)
                elif recurrence_type == 'monthly':
                    # Add months while preserving day of month
                    new_month = current_date.month + recurrence_interval
                    new_year = current_date.year + (new_month - 1) // 12
                    new_month = ((new_month - 1) % 12) + 1
                    try:
                        current_date = current_date.replace(year=new_year, month=new_month)
                    except ValueError:
                        # Handle day overflow (e.g., Jan 31 -> Feb 28)
                        max_day = calendar.monthrange(new_year, new_month)[1]
                        current_date = current_date.replace(year=new_year, month=new_month, day=min(current_date.day, max_day))
            except Exception as e:
                print(f"Error calculating next occurrence: {e}")
                break
            continue
        
        # Create instance for this occurrence
        instance_start = datetime.combine(current_date, start_time)
        instance_end = datetime.combine(current_date, end_time)
        
        # Handle case where end time is next day
        if end_time < start_time:
            instance_end = datetime.combine(current_date + timedelta(days=1), end_time)
        
        instance_id = str(uuid.uuid4())
        instance = {
            'id': instance_id,
            'title': pattern['title'],
            'start': instance_start.strftime('%Y-%m-%dT%H:%M'),
            'end': instance_end.strftime('%Y-%m-%dT%H:%M'),
            'location': pattern.get('location', ''),
            'description': pattern.get('description', ''),
            'all_day': pattern.get('all_day', False),
            'layer': pattern.get('layer', 'personal'),
            'is_recurring_instance': True,
            'pattern_id': pattern['id'],
            'occurrence_date': current_date.isoformat(),
            'created_at': datetime.now().isoformat()
        }
        
        instances.append(instance)
        
        # Calculate next occurrence
        try:
            if recurrence_type == 'daily':
                current_date += timedelta(days=recurrence_interval)
            elif recurrence_type == 'weekly':
                current_date += timedelta(weeks=recurrence_interval)
            elif recurrence_type == 'monthly':
                # Add months while preserving day of month
                new_month = current_date.month + recurrence_interval
                new_year = current_date.year + (new_month - 1) // 12
                new_month = ((new_month - 1) % 12) + 1
                try:
                    current_date = current_date.replace(year=new_year, month=new_month)
                except ValueError:
                    # Handle day overflow (e.g., Jan 31 -> Feb 28)
                    max_day = calendar.monthrange(new_year, new_month)[1]
                    current_date = current_date.replace(year=new_year, month=new_month, day=min(current_date.day, max_day))
        except Exception as e:
            print(f"Error calculating next occurrence: {e}")
            break
        
        count += 1
    
    return instances

@app.route('/')
def index():
    return render_template('index.html')

# Layer Management Routes
@app.route('/api/layers', methods=['GET'])
def get_layers():
    """Get all layers"""
    layers = load_layers()
    return jsonify(list(layers.values()))

@app.route('/api/layers', methods=['POST'])
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
    
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    tasks = load_tasks()
    ymd = request.args.get('date')
    if ymd:
        filtered = [t for t in tasks.values() if t.get('date') == ymd]
        return jsonify(filtered)
    return jsonify(list(tasks.values()))

@app.route('/api/tasks', methods=['POST'])
def create_task():
    tasks = load_tasks()
    data = request.json
    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'title': data.get('title', ''),
        'details': data.get('details', ''),
        'status': data.get('status', 'Planned'),
        'date': data.get('date'),  # YYYY-MM-DD string
        'due_at': data.get('when'), # can be null or ISO string
        'committed_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat()
    }
    tasks[task_id] = task
    save_tasks(tasks)
    return jsonify(task), 201

@app.route('/api/tasks/<task_id>', methods=['PATCH', 'PUT'])
def update_task(task_id):
    tasks = load_tasks()
    if task_id not in tasks:
        return jsonify({'error': 'Task not found'}), 404
    data = request.json
    task = tasks[task_id]
    for key in ['title', 'details', 'status', 'date', 'due_at']:
        if key in data:
            task[key] = data[key]
    task['updated_at'] = datetime.now().isoformat()
    tasks[task_id] = task
    save_tasks(tasks)
    return jsonify(task)

@app.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    tasks = load_tasks()
    if task_id not in tasks:
        return jsonify({'error': 'Task not found'}), 404
    del tasks[task_id]
    save_tasks(tasks)
    return jsonify({'message': 'Deleted'}), 200

@app.route('/api/layers/<layer_id>', methods=['PUT'])
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

@app.route('/api/layers/<layer_id>', methods=['DELETE'])
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

@app.route('/api/recurring-patterns/<pattern_id>', methods=['GET'])
def get_recurring_pattern(pattern_id):
    pats = load_recurring_patterns()
    if pattern_id not in pats:
        return jsonify({'error': 'Pattern not found'}), 404
    return jsonify(pats[pattern_id])

# Recurring Pattern Routes
@app.route('/api/recurring-patterns', methods=['GET'])
def get_recurring_patterns():
    """Get all recurring patterns + their layer info + exceptions"""
    patterns = load_recurring_patterns()
    layers = load_layers()
    events = load_events()  # <-- read events to find exceptions

    pattern_list = []
    for pattern in patterns.values():
        pattern_copy = pattern.copy()

        # layer metadata
        layer_id = pattern.get('layer', 'personal')
        if layer_id in layers:
            pattern_copy['layer_color'] = layers[layer_id]['color']
            pattern_copy['layer_name']  = layers[layer_id]['name']

        # build exceptions for this pattern
        pid = pattern['id']
        deletion_exceptions = []
        moved_exceptions = []

        for ev in events.values():
            if ev.get('is_deletion_exception') and ev.get('original_pattern_id') == pid:
                deletion_exceptions.append({
                    'id': ev['id'],
                    'original_occurrence_date': ev.get('original_occurrence_date'),
                })
            if ev.get('is_moved_exception') and ev.get('original_pattern_id') == pid:
                moved_exceptions.append({
                    'id': ev['id'],
                    'original_occurrence_date': ev.get('original_occurrence_date'),
                    'new_start': ev.get('start'),
                    'new_end': ev.get('end'),
                    'title': ev.get('title', pattern.get('title', '')),
                    'layer': ev.get('layer', layer_id),
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

@app.route('/api/recurring-patterns', methods=['POST'])
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

@app.route('/api/recurring-patterns/<pattern_id>', methods=['PUT'])
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
    
@app.route('/api/recurring/<pattern_id>', methods=['DELETE'])
def delete_recurring_event(pattern_id):
    patterns = load_recurring_patterns()
    events = load_events()

    # 1. Remove the pattern itself
    if pattern_id in patterns:
        del patterns[pattern_id]
        save_recurring_patterns(patterns)

    # 2. Remove any exception events linked to this pattern
    to_delete = []
    for eid, ev in events.items():
        if ev.get('original_pattern_id') == pattern_id:
            to_delete.append(eid)

    for eid in to_delete:
        del events[eid]

    save_events(events)

    return jsonify({"success": True, "deleted_pattern": pattern_id, "deleted_exceptions": len(to_delete)})


@app.route('/api/recurring-patterns/<pattern_id>', methods=['DELETE'])
def delete_recurring_pattern(pattern_id):
    """Delete a recurring pattern"""
    patterns = load_recurring_patterns()
    if pattern_id not in patterns:
        return jsonify({'error': 'Pattern not found'}), 404
    
    del patterns[pattern_id]
    
    if save_recurring_patterns(patterns):
        return jsonify({'message': 'Pattern deleted'}), 200
    else:
        return jsonify({'error': 'Failed to delete pattern'}), 500

# helper (keep as you already added)
def _recurrence_text(p):
    t = p.get('recurrence_type', 'weekly')
    n = int(p.get('recurrence_interval', 1))
    if t == 'daily':
        head = 'Daily' if n == 1 else f'Every {n} day(s)'
    elif t == 'monthly':
        head = 'Monthly' if n == 1 else f'Every {n} month(s)'
    else:
        head = 'Weekly' if n == 1 else f'Every {n} week(s)'
    et = p.get('recurrence_end_type', 'never')
    if et == 'count':
        head += f", {p.get('recurrence_end_count', 0)} times"
    elif et == 'date' and p.get('recurrence_end_date'):
        head += f", until {p['recurrence_end_date']}"
    return head

@app.route('/api/events', methods=['GET'])
def get_events():
    """Get all events (regular events + generated recurring instances) with layer filtering and series enrichment"""
    events   = load_events()
    patterns = load_recurring_patterns()
    layers   = load_layers()

    def _is_orphan_exception(ev: dict) -> bool:
        """True if this event references a series that no longer exists AND it's an exception/instance."""
        pid = ev.get('pattern_id') or ev.get('original_pattern_id')
        if not pid:
            return False
        if pid in patterns:
            return False
        # Treat any deletion/moved/instance as orphan exception if series is gone
        return bool(
            ev.get('is_deletion_exception') or
            ev.get('is_moved_exception') or
            ev.get('is_recurring_instance')
        )

    # 1) Start with regular events (copy), drop deletion markers and orphaned exceptions
    all_events = {}
    for eid, ev in events.items():
        if ev.get('is_deletion_exception', False):
            continue  # never show deletion markers
        if _is_orphan_exception(ev):
            continue  # safety-net: hide orphaned exceptions
        all_events[eid] = ev  # keep as-is (we'll copy when enriching)

    # 2) Generate instances from recurring patterns (always normalized flags)
    for pattern in patterns.values():
        instances = generate_instances_from_pattern(pattern)
        for instance in instances:
            inst = instance.copy()
            inst['is_recurring_instance'] = True
            inst['is_moved_exception']    = bool(inst.get('is_moved_exception', False))
            inst['is_deletion_exception'] = False
            all_events[inst['id']] = inst

    # 3) Enrich with series info + stable flags (work on copies so we don't mutate disk data)
    enriched_events = []
    for ev in all_events.values():
        ev_out = ev.copy()

        # Normalize booleans
        ev_out['is_recurring_instance'] = bool(ev_out.get('is_recurring_instance', False))
        ev_out['is_moved_exception']    = bool(ev_out.get('is_moved_exception', False))
        ev_out['is_deletion_exception'] = bool(ev_out.get('is_deletion_exception', False))

        # Series enrichment
        pid = ev_out.get('pattern_id') or ev_out.get('original_pattern_id')
        if pid and pid in patterns:
            p = patterns[pid]
            ev_out['series'] = {
                'id': p['id'],
                'title': p.get('title', ''),
                'first_occurrence': p.get('first_occurrence'),
                'start_time': p.get('start_time'),
                'recurrence_text': _recurrence_text(p),
            }
            ev_out['is_recurring_linked'] = True
        else:
            ev_out['is_recurring_linked'] = False

        enriched_events.append(ev_out)

    # 4) Filter by visible layers + attach layer metadata
    visible_layers = [lid for lid, l in layers.items() if l.get('visible', True)]
    filtered_events = []
    for ev in enriched_events:
        layer_id = ev.get('layer', 'personal')
        if layer_id in visible_layers:
            ev_out = ev.copy()
            if layer_id in layers:
                ev_out['layer_color'] = layers[layer_id]['color']
                ev_out['layer_name']  = layers[layer_id]['name']
            filtered_events.append(ev_out)

    return jsonify(filtered_events)

@app.route('/api/events', methods=['POST'])
def create_event():
    """Create a new event (regular or create recurring pattern)"""
    data = request.json
    
    if data.get('is_recurring', False):
        # Create recurring pattern instead of regular event
        return create_recurring_pattern()
    else:
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
    # NEW: exception metadata
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

@app.route('/api/events/<event_id>', methods=['PUT'])
def update_event(event_id):
    events = load_events()
    if event_id not in events:
        return jsonify({'error': 'Event not found'}), 404

    data = request.json
    ev = events[event_id]

    def provided(key):
        # help distinguish between "not provided" and "provided as null/false"
        return key in data

    # regular fields
    if provided('title'): ev['title'] = data['title']
    if provided('start'): ev['start'] = data['start']
    if provided('end'): ev['end'] = data['end']
    if provided('location'): ev['location'] = data['location']
    if provided('description'): ev['description'] = data['description']
    if provided('all_day'): ev['all_day'] = data['all_day']
    if provided('layer'): ev['layer'] = data['layer']

    # exception metadata (allow clearing)
    if provided('is_deletion_exception'): ev['is_deletion_exception'] = data['is_deletion_exception']
    if provided('is_moved_exception'): ev['is_moved_exception'] = data['is_moved_exception']
    if provided('original_pattern_id'): ev['original_pattern_id'] = data['original_pattern_id']
    if provided('original_occurrence_date'): ev['original_occurrence_date'] = data['original_occurrence_date']

    ev['updated_at'] = datetime.now().isoformat()

    if save_events(events):
        return jsonify(ev)
    return jsonify({'error': 'Failed to update event'}), 500


@app.route('/api/events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    """Delete an event (regular event or recurring pattern)"""
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

# Legacy compatibility route
@app.route('/api/recurring-events', methods=['GET'])
def get_recurring_events():
    """Legacy route - redirects to recurring patterns"""
    return get_recurring_patterns()

# --- helper: human text for a pattern (put this near your other helpers) ---
def _recurrence_text(p):
    t = p.get('recurrence_type', 'weekly')
    n = int(p.get('recurrence_interval', 1))
    if t == 'daily':
        base = 'day(s)'; head = 'Daily' if n == 1 else f'Every {n} {base}'
    elif t == 'monthly':
        base = 'month(s)'; head = 'Monthly' if n == 1 else f'Every {n} {base}'
    else:
        base = 'week(s)'; head = 'Weekly' if n == 1 else f'Every {n} {base}'

    et = p.get('recurrence_end_type', 'never')
    if et == 'count':
        head += f", {p.get('recurrence_end_count', 0)} times"
    elif et == 'date' and p.get('recurrence_end_date'):
        head += f", until {p['recurrence_end_date']}"
    return head



if __name__ == '__main__':
    app.run(debug=True)