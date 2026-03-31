from enum import Enum

class Monitoring(Enum):
    INTERVAL = 60 
    CPU_THRESHOLD = 90.0 
    MEMORY_THRESHOLD = 80.0 
    DISK_THRESHOLD = 90.0 
    TEMPERATURE_THRESHOLD = 80.0 

class WzRegistration(Enum):
    MAX_REGISTRATION_ROLES = 4
    MIN_REGISTRATION_ROLES = 1

class Bot(Enum):
    DEFAULT_PREFIX = "!"
    
    DELAY = 0.1

    pass



