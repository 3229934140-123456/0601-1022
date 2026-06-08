import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional


class AuditManager:
    """数据处理审计管理器，记录每次数据操作的输入输出链路"""

    def __init__(self, audit_file: Path):
        self.audit_file = Path(audit_file)
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)

    def record(self, command: str, input_files: List[str], output_file: str,
               row_count: int = 0, total_emissions: float = 0.0,
               parameters: Dict = None, status: str = 'success',
               message: str = '') -> str:
        """记录一条审计记录，返回记录 ID"""
        record_id = str(uuid.uuid4())[:12]
        record = {
            'id': record_id,
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'command': command,
            'input_files': input_files or [],
            'output_file': output_file,
            'row_count': row_count,
            'total_emissions': round(total_emissions, 6),
            'parameters': parameters or {},
            'status': status,
            'message': message,
        }
        with open(self.audit_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return record_id

    def list_records(self, limit: int = 50, command: str = None) -> List[Dict]:
        """列出最近的审计记录"""
        records = self._load_all()
        if command:
            records = [r for r in records if command in r.get('command', '')]
        return records[-limit:]

    def get_record(self, record_id: str) -> Optional[Dict]:
        """根据 ID 获取单条记录"""
        records = self._load_all()
        for r in records:
            if r.get('id', '').startswith(record_id):
                return r
        return None

    def trace_file(self, file_name: str, max_depth: int = 10) -> List[Dict]:
        """追踪一个文件的上游数据链路（向前追溯）"""
        records = self._load_all()
        chain = []
        current = file_name
        visited = set()

        for _ in range(max_depth):
            found = None
            for r in reversed(records):
                out_file = Path(r.get('output_file', '')).name
                if out_file == current and r.get('id') not in visited:
                    found = r
                    break
            if not found:
                break
            chain.append(found)
            visited.add(found['id'])
            inputs = found.get('input_files', [])
            if inputs:
                current = Path(inputs[0]).name
            else:
                break

        return list(reversed(chain))

    def _load_all(self) -> List[Dict]:
        """加载所有审计记录"""
        records = []
        if not self.audit_file.exists():
            return records
        with open(self.audit_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records
