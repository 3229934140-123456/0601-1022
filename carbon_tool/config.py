import os
import yaml
from pathlib import Path


class Config:
    DEFAULT_CONFIG = {
        'project_name': 'carbon-project',
        'data_dir': 'data',
        'output_dir': 'output',
        'logs_dir': 'logs',
        'factors_file': 'factors.yaml',
        'mapping_file': 'field_mapping.yaml',
        'targets_file': 'targets.yaml',
        'reductions_file': 'reductions.yaml',
    }

    def __init__(self, project_path=None):
        self.project_path = Path(project_path or os.getcwd())
        self.config_file = self.project_path / '.carbon-config.yaml'
        self._config = None

    @property
    def config(self):
        if self._config is None:
            self.load()
        return self._config

    def load(self):
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = self.DEFAULT_CONFIG.copy()
        return self._config

    def save(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def get_path(self, key):
        value = self.get(key)
        if value:
            return self.project_path / value
        return None

    @property
    def data_dir(self):
        return self.project_path / self.get('data_dir', 'data')

    @property
    def output_dir(self):
        return self.project_path / self.get('output_dir', 'output')

    @property
    def logs_dir(self):
        return self.project_path / self.get('logs_dir', 'logs')

    @property
    def factors_file(self):
        return self.project_path / self.get('factors_file', 'factors.yaml')

    @property
    def mapping_file(self):
        return self.project_path / self.get('mapping_file', 'field_mapping.yaml')

    @property
    def targets_file(self):
        return self.project_path / self.get('targets_file', 'targets.yaml')

    @property
    def reductions_file(self):
        return self.project_path / self.get('reductions_file', 'reductions.yaml')

    def is_initialized(self):
        return self.config_file.exists()

    def ensure_dirs(self):
        for d in [self.data_dir, self.output_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)
