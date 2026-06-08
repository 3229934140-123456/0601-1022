import yaml
import uuid
from pathlib import Path
from typing import List, Dict, Optional
from .models import EmissionFactor, FieldMapping, Target, ReductionRecord, ProductAllocation


class DataManager:
    def __init__(self, config):
        self.config = config

    def load_factors(self) -> Dict[str, EmissionFactor]:
        data = {}
        if self.config.factors_file.exists():
            with open(self.config.factors_file, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or {}
            for name, info in raw.items():
                data[name] = EmissionFactor(
                    name=name,
                    factor=float(info.get('factor', 0)),
                    unit=info.get('unit', ''),
                    scope=info.get('scope', ''),
                    category=info.get('category', ''),
                    description=info.get('description', ''),
                    tags=info.get('tags', {}) or {},
                )
        return data

    def save_factors(self, factors: Dict[str, EmissionFactor]):
        data = {}
        for name, ef in factors.items():
            data[name] = {
                'factor': ef.factor,
                'unit': ef.unit,
                'scope': ef.scope,
                'category': ef.category,
                'description': ef.description,
                'tags': ef.tags,
            }
        self.config.factors_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.factors_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def add_factor(self, factor: EmissionFactor):
        factors = self.load_factors()
        factors[factor.name] = factor
        self.save_factors(factors)

    def delete_factor(self, name: str) -> bool:
        factors = self.load_factors()
        if name in factors:
            del factors[name]
            self.save_factors(factors)
            return True
        return False

    def get_factor(self, name: str) -> Optional[EmissionFactor]:
        factors = self.load_factors()
        return factors.get(name)

    def find_factors(self, source_type: str, tags: Dict[str, str] = None) -> List[EmissionFactor]:
        """按能源类型和标签查找候选因子（按匹配度排序）"""
        factors = self.load_factors()
        candidates = []
        for name, ef in factors.items():
            if source_type and source_type.lower() in name.lower():
                candidates.append(ef)
                continue
            if ef.category and source_type and source_type.lower() in ef.category.lower():
                candidates.append(ef)
                continue
        if tags:
            scored = []
            for ef in candidates:
                match_count = sum(
                    1 for k, v in tags.items()
                    if k in ef.tags and str(ef.tags[k]).lower() == str(v).lower()
                )
                if match_count > 0 or not candidates:
                    scored.append((match_count, ef))
            scored.sort(key=lambda x: -x[0])
            return [ef for _, ef in scored]
        return candidates

    def load_mapping(self) -> List[FieldMapping]:
        data = []
        if self.config.mapping_file.exists():
            with open(self.config.mapping_file, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or []
            for item in raw:
                data.append(FieldMapping(
                    source_field=item.get('source_field', ''),
                    target_field=item.get('target_field', ''),
                    data_type=item.get('data_type', 'string'),
                    required=item.get('required', False),
                ))
        return data

    def save_mapping(self, mappings: List[FieldMapping]):
        data = []
        for m in mappings:
            data.append({
                'source_field': m.source_field,
                'target_field': m.target_field,
                'data_type': m.data_type,
                'required': m.required,
            })
        self.config.mapping_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.mapping_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def load_targets(self) -> List[Target]:
        data = []
        if self.config.targets_file.exists():
            with open(self.config.targets_file, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or []
            for item in raw:
                data.append(Target(
                    year=int(item.get('year', 0)),
                    scope1_target=float(item.get('scope1_target', 0)),
                    scope2_target=float(item.get('scope2_target', 0)),
                    scope3_target=float(item.get('scope3_target', 0)),
                    total_target=float(item.get('total_target', 0)),
                    unit=item.get('unit', 'tCO2e'),
                    description=item.get('description', ''),
                ))
        return data

    def save_targets(self, targets: List[Target]):
        data = []
        for t in targets:
            data.append({
                'year': t.year,
                'scope1_target': t.scope1_target,
                'scope2_target': t.scope2_target,
                'scope3_target': t.scope3_target,
                'total_target': t.total_target,
                'unit': t.unit,
                'description': t.description,
            })
        self.config.targets_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.targets_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def add_target(self, target: Target):
        targets = self.load_targets()
        existing = next((t for t in targets if t.year == target.year), None)
        if existing:
            targets = [t for t in targets if t.year != target.year]
        targets.append(target)
        targets.sort(key=lambda x: x.year)
        self.save_targets(targets)

    def load_reductions(self) -> List[ReductionRecord]:
        data = []
        if self.config.reductions_file.exists():
            with open(self.config.reductions_file, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or []
            for item in raw:
                data.append(ReductionRecord(
                    id=item.get('id', str(uuid.uuid4())[:8]),
                    date=item.get('date', ''),
                    measure=item.get('measure', ''),
                    reduction_amount=float(item.get('reduction_amount', 0)),
                    unit=item.get('unit', 'tCO2e'),
                    department=item.get('department', ''),
                    description=item.get('description', ''),
                ))
        return data

    def save_reductions(self, reductions: List[ReductionRecord]):
        data = []
        for r in reductions:
            data.append({
                'id': r.id or str(uuid.uuid4())[:8],
                'date': r.date,
                'measure': r.measure,
                'reduction_amount': r.reduction_amount,
                'unit': r.unit,
                'department': r.department,
                'description': r.description,
            })
        self.config.reductions_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.reductions_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def add_reduction(self, record: ReductionRecord):
        reductions = self.load_reductions()
        if not record.id:
            record.id = str(uuid.uuid4())[:8]
        reductions.append(record)
        self.save_reductions(reductions)
        return record.id

    def load_allocations(self) -> List[ProductAllocation]:
        data = []
        if self.config.allocations_file.exists():
            with open(self.config.allocations_file, 'r', encoding='utf-8') as f:
                raw = yaml.safe_load(f) or []
            for item in raw:
                data.append(ProductAllocation(
                    product=item.get('product', ''),
                    allocation_ratio=float(item.get('allocation_ratio', 0)),
                    department=item.get('department', ''),
                ))
        return data

    def save_allocations(self, allocations: List[ProductAllocation]):
        data = []
        for a in allocations:
            data.append({
                'product': a.product,
                'allocation_ratio': a.allocation_ratio,
                'department': a.department,
            })
        self.config.allocations_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.allocations_file, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
