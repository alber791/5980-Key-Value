import threading


class KeyValueStore:
    def __init__(self):
        # In-memory storage
        self._store = {}
        # Lock for thread safety
        self._lock = threading.Lock()

    def get(self, key):
        # Gets the value for given key, null otherwise
        with self._lock:
            return self._store.get(key)

    def put(self, key, value):
        # Store a value for given key, overwriting if necessary
        # Always returns True
        with self._lock:
            self._store[key] = value
        return True

    def delete(self, key):
        # Removes a key and its value
        # True if key-value was deleted, false otherwise
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def exists(self, key):
        # Checks if a key exists in the store
        with self._lock:
            return key in self._store