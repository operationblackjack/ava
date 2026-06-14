import re
import json
from pathlib import Path
from core.llm import LLM
from core.memory import Memory

def handle_debug_error(rest: str, mem: dict) -> str:
    """
    Handles the debug error command.
    
    This function takes in an error message as input, parses it, and then provides 
    more tailored advice based on the error message.
    
    Parameters:
    rest (str): The error message to be parsed.
    mem (dict): The memory dictionary.
    
    Returns:
    str: The advice based on the error message.
    """
    # Parse the error message
    error_message = rest.strip()
    
    # Check if the error message contains a specific error code
    error_code_match = re.search(r"error code (\d+)", error_message, re.IGNORECASE)
    if error_code_match:
        error_code = error_code_match.group(1)
        # Provide advice based on the error code
        if error_code == "1":
            return "Error code 1 usually indicates a syntax error. Please check your code for any syntax mistakes."
        elif error_code == "2":
            return "Error code 2 usually indicates a runtime error. Please check your code for any runtime errors."
        else:
            return "Unknown error code. Please provide more information about the error."
    else:
        # If no error code is found, try to match the error message with a known error pattern
        error_patterns = {
            r"cannot find module": "The module you are trying to import is not installed. Please install it using pip.",
            r"syntax error": "There is a syntax error in your code. Please check your code for any syntax mistakes.",
            r"runtime error": "There is a runtime error in your code. Please check your code for any runtime errors."
        }
        for pattern, advice in error_patterns.items():
            if re.search(pattern, error_message, re.IGNORECASE):
                return advice
    
    # If no match is found, provide a generic advice
    return "Unknown error. Please provide more information about the error."

def register() -> dict:
    """
    Registers the plugin.
    
    Returns:
    dict: A dictionary containing the commands and description of the plugin.
    """
    return {
        "commands": ["debug error"],
        "description": "A simple debugging tool that can parse and analyze error messages to provide more tailored advice."
    }