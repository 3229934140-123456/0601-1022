import os
import json
from datetime import datetime
from pathlib import Path


class CommandLogger:
    def __init__(self, logs_dir):
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.logs_dir / 'commands.log'

    def log(self, command, args, status, message='', details=None):
        entry = {
            'timestamp': datetime.now().isoformat(),
            'command': command,
            'args': args,
            'status': status,
            'message': message,
            'details': details or {},
        }
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    def list_logs(self, limit=50, command_filter=None):
        logs = []
        if not self.log_file.exists():
            return logs
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if command_filter and entry.get('command') != command_filter:
                            continue
                        logs.append(entry)
                    except json.JSONDecodeError:
                        continue
        return logs[-limit:]

    def clear_logs(self):
        if self.log_file.exists():
            self.log_file.unlink()
            return True
        return False
