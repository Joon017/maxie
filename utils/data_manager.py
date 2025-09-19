# utils/data_manager.py - Data Storage Management
import json
import os
from datetime import datetime

# File paths
DATA_DIR = 'data'
EVENTS_FILE = os.path.join(DATA_DIR, 'events.json')
PATTERNS_FILE = os.path.join(DATA_DIR, 'recurring_patterns.json')
LAYERS_FILE = os.path.join(DATA_DIR, 'layers.json')
TASKS_FILE = os.path.join(DATA_DIR, 'tasks.json')

# Default layers configuration
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
    os.makedirs(DATA_DIR, exist_ok=True)

def load_json_file(filepath, default_data=None):
    """Generic function to load JSON files"""
    ensure_data_directory()
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
        return default_data or {}
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return default_data or {}

def save_json_file(filepath, data):
    """Generic function to save JSON files"""
    ensure_data_directory()
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {filepath}: {e}")
        return False

# Specific data loaders and savers
def load_events():
    """Load event instances from JSON file"""
    return load_json_file(EVENTS_FILE)

def save_events(events_dict):
    """Save event instances to JSON file"""
    return save_json_file(EVENTS_FILE, events_dict)

def load_recurring_patterns():
    """Load recurring patterns from JSON file"""
    return load_json_file(PATTERNS_FILE)

def save_recurring_patterns(patterns_dict):
    """Save recurring patterns to JSON file"""
    return save_json_file(PATTERNS_FILE, patterns_dict)

def load_layers():
    """Load layers from JSON file"""
    layers = load_json_file(LAYERS_FILE)
    if not layers:
        # Initialize with default layers
        save_layers(DEFAULT_LAYERS)
        return DEFAULT_LAYERS.copy()
    return layers

def save_layers(layers_dict):
    """Save layers to JSON file"""
    return save_json_file(LAYERS_FILE, layers_dict)

def load_tasks():
    """Load tasks from JSON file"""
    return load_json_file(TASKS_FILE)

def save_tasks(tasks_dict):
    """Save tasks to JSON file"""
    return save_json_file(TASKS_FILE, tasks_dict)