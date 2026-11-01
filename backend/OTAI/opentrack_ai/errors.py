"""Dependency-free API errors and shared native-parser lock."""
import threading

LOCK = threading.RLock()

class APIError(Exception):
    def __init__(self,code,message,details=None):
        super().__init__(message);self.code=code;self.details=details
    def as_dict(self):return {'code':self.code,'message':str(self),'details':self.details}

