# utils/recurring_utils.py - Recurring Events Logic
from datetime import datetime, timedelta
import calendar
import uuid
from .data_manager import load_events

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
            current_date = calculate_next_occurrence(current_date, recurrence_type, recurrence_interval)
            if current_date is None:
                break
            continue
        
        # Create instance for this occurrence
        instance = create_instance_from_pattern(pattern, current_date, start_time, end_time)
        instances.append(instance)
        
        # Calculate next occurrence
        current_date = calculate_next_occurrence(current_date, recurrence_type, recurrence_interval)
        if current_date is None:
            break
        
        count += 1
    
    return instances

def create_instance_from_pattern(pattern, current_date, start_time, end_time):
    """Create a single instance from pattern and date"""
    instance_start = datetime.combine(current_date, start_time)
    instance_end = datetime.combine(current_date, end_time)
    
    # Handle case where end time is next day
    if end_time < start_time:
        instance_end = datetime.combine(current_date + timedelta(days=1), end_time)
    
    instance_id = str(uuid.uuid4())
    return {
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

def calculate_next_occurrence(current_date, recurrence_type, recurrence_interval):
    """Calculate the next occurrence date based on recurrence rules"""
    try:
        if recurrence_type == 'daily':
            return current_date + timedelta(days=recurrence_interval)
        elif recurrence_type == 'weekly':
            return current_date + timedelta(weeks=recurrence_interval)
        elif recurrence_type == 'monthly':
            # Add months while preserving day of month
            new_month = current_date.month + recurrence_interval
            new_year = current_date.year + (new_month - 1) // 12
            new_month = ((new_month - 1) % 12) + 1
            try:
                return current_date.replace(year=new_year, month=new_month)
            except ValueError:
                # Handle day overflow (e.g., Jan 31 -> Feb 28)
                max_day = calendar.monthrange(new_year, new_month)[1]
                return current_date.replace(year=new_year, month=new_month, day=min(current_date.day, max_day))
    except Exception as e:
        print(f"Error calculating next occurrence: {e}")
        return None

def get_recurrence_text(pattern):
    """Generate human-readable recurrence description"""
    recurrence_type = pattern.get('recurrence_type', 'weekly')
    interval = int(pattern.get('recurrence_interval', 1))
    end_type = pattern.get('recurrence_end_type', 'never')
    end_count = pattern.get('recurrence_end_count')
    end_date = pattern.get('recurrence_end_date')
    
    if recurrence_type == 'daily':
        base = 'day(s)'
        head = 'Daily' if interval == 1 else f'Every {interval} {base}'
    elif recurrence_type == 'monthly':
        base = 'month(s)'
        head = 'Monthly' if interval == 1 else f'Every {interval} {base}'
    else:
        base = 'week(s)'
        head = 'Weekly' if interval == 1 else f'Every {interval} {base}'

    if end_type == 'count':
        head += f", {end_count} times"
    elif end_type == 'date' and end_date:
        head += f", until {end_date}"
        
    return head