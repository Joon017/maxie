# api/tasks.py - Tasks API Blueprint
from flask import Blueprint, request, jsonify
from datetime import datetime
import uuid
from utils.data_manager import load_tasks, save_tasks

tasks_bp = Blueprint('tasks', __name__)

@tasks_bp.route('/tasks', methods=['GET'])
def get_tasks():
    """Get all tasks, optionally filtered by date"""
    tasks = load_tasks()
    ymd = request.args.get('date')
    
    if ymd:
        # Filter tasks for specific date
        filtered = [task for task in tasks.values() if task.get('date') == ymd]
        return jsonify(filtered)
    
    return jsonify(list(tasks.values()))

@tasks_bp.route('/tasks', methods=['POST'])
def create_task():
    """Create a new task"""
    tasks = load_tasks()
    data = request.json
    task_id = str(uuid.uuid4())
    
    task = {
        'id': task_id,
        'title': data.get('title', ''),
        'details': data.get('details', ''),
        'status': data.get('status', 'planned'),
        'date': data.get('date'),  # YYYY-MM-DD string
        'due_at': data.get('due_at'),  # can be null or ISO string
        'committed_at': data.get('committed_at', datetime.now().isoformat()),
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat()
    }
    
    tasks[task_id] = task
    
    if save_tasks(tasks):
        return jsonify(task), 201
    else:
        return jsonify({'error': 'Failed to save task'}), 500

@tasks_bp.route('/tasks/<task_id>', methods=['PATCH', 'PUT'])
def update_task(task_id):
    """Update a task"""
    tasks = load_tasks()
    if task_id not in tasks:
        return jsonify({'error': 'Task not found'}), 404
    
    data = request.json
    task = tasks[task_id]
    
    # Update allowed fields
    updatable_fields = ['title', 'details', 'status', 'date', 'due_at']
    for key in updatable_fields:
        if key in data:
            task[key] = data[key]
    
    task['updated_at'] = datetime.now().isoformat()
    tasks[task_id] = task
    
    if save_tasks(tasks):
        return jsonify(task)
    else:
        return jsonify({'error': 'Failed to update task'}), 500

@tasks_bp.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """Delete a task"""
    tasks = load_tasks()
    if task_id not in tasks:
        return jsonify({'error': 'Task not found'}), 404
    
    del tasks[task_id]
    
    if save_tasks(tasks):
        return jsonify({'message': 'Task deleted successfully'}), 200
    else:
        return jsonify({'error': 'Failed to delete task'}), 500