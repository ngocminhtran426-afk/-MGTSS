import os
import time
import functools

def except_handler(retry=3, delay=2):
    """
    Retry decorator with exponential backoff.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = delay
            while attempts < retry:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    if attempts == retry:
                        print(f"Error in {func.__name__} after {retry} attempts: {e}")
                        raise
                    print(f"Attempt {attempts} failed for {func.__name__}. Retrying in {current_delay}s... Error: {e}")
                    time.sleep(current_delay)
                    current_delay *= 2
        return wrapper
    return decorator

def check_file_exists(file_arg_index=None, file_kwarg=None):
    """
    Decorator to skip execution if output file already exists (Resume capability).
    Can specify the file path argument by index or keyword.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            file_path = None
            if file_kwarg and file_kwarg in kwargs:
                file_path = kwargs[file_kwarg]
            elif file_arg_index is not None and file_arg_index < len(args):
                file_path = args[file_arg_index]
                
            if file_path and os.path.exists(file_path):
                print(f"Skipping {func.__name__} as file already exists: {file_path}")
                return file_path
                
            return func(*args, **kwargs)
        return wrapper
    return decorator
