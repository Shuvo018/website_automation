from types import SimpleNamespace
import logging
from threading import Event

shared_state = SimpleNamespace(
    flag=False,
    last_point_value=None
    )
start_task_event = Event()

def read_credentials(file_path='idpass.txt'):
    credentials = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    credentials[key] = value
    except Exception as e:
        logging.error(f"Error reading credentials from file: {e}")
    return credentials