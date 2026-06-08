import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pandas as pd


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
        """追踪一个文件的上游数据链路（线性链路，取主输入）"""
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

    def trace_file_tree(self, file_name: str, max_depth: int = 10) -> Optional[Dict]:
        """追踪一个文件的完整上游数据树（递归展开所有输入）

        返回结构:
        {
            'file_name': 'xxx.csv',
            'record': {...},           # 产生该文件的审计记录（可能为 None，如果是最原始输入）
            'is_original': bool,       # 是否是最原始输入（无上游）
            'sources': [...]           # import 文件特有的：来源文件/工作表/行号
            'inputs': [...]            # 上游输入节点列表
        }
        """
        records = self._load_all()
        visited_ids = set()

        def _trace(fname: str, depth: int) -> Optional[Dict]:
            if depth <= 0:
                return None

            found = None
            for r in reversed(records):
                out_file = Path(r.get('output_file', '')).name
                if out_file == fname and r.get('id') not in visited_ids:
                    found = r
                    break

            if not found:
                node = {
                    'file_name': fname,
                    'record': None,
                    'is_original': True,
                    'sources': self._extract_csv_sources(fname),
                    'inputs': [],
                }
                return node

            visited_ids.add(found['id'])

            input_nodes = []
            for inp in found.get('input_files', []):
                inp_name = Path(inp).name
                child = _trace(inp_name, depth - 1)
                if child:
                    input_nodes.append(child)

            node = {
                'file_name': fname,
                'record': found,
                'is_original': False,
                'sources': self._extract_csv_sources(found.get('output_file', '')),
                'inputs': input_nodes,
            }
            return node

        return _trace(file_name, max_depth)

    def _extract_csv_sources(self, file_path: str) -> List[Dict]:
        """从 CSV 文件中提取来源文件/工作表/行号范围（import 产生的文件才有这些列）"""
        try:
            p = Path(file_path)
            if not p.exists() or p.suffix.lower() != '.csv':
                return []

            df = pd.read_csv(p, nrows=0, encoding='utf-8-sig')
            needed = {'source_file', 'source_sheet', 'source_row'}
            if not needed.issubset(set(df.columns)):
                return []

            df_full = pd.read_csv(p, encoding='utf-8-sig',
                                  usecols=['source_file', 'source_sheet', 'source_row'])
            df_full['source_sheet'] = df_full['source_sheet'].fillna('')
            df_full['source_file'] = df_full['source_file'].fillna('')

            sources = []
            grouped = df_full.groupby(['source_file', 'source_sheet'])
            for (sf, ss), group in grouped:
                min_row = int(group['source_row'].min())
                max_row = int(group['source_row'].max())
                row_count = len(group)
                sources.append({
                    'source_file': str(sf),
                    'source_sheet': str(ss) if ss else '',
                    'min_row': min_row,
                    'max_row': max_row,
                    'row_count': row_count,
                })
            return sources
        except Exception:
            return []

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
