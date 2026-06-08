from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum


class Scope(Enum):
    SCOPE1 = "范围1"
    SCOPE2 = "范围2"
    SCOPE3 = "范围3"


class EmissionCategory(Enum):
    STATIONARY_COMBUSTION = "固定燃烧"
    MOBILE_COMBUSTION = "移动燃烧"
    PROCESS_EMISSIONS = "过程排放"
    FUGITIVE_EMISSIONS = "逃逸排放"
    PURCHASED_ELECTRICITY = "外购电力"
    PURCHASED_HEAT = "外购热力"
    PURCHASED_STEAM = "外购蒸汽"
    UPSTREAM_TRANSPORTATION = "上游运输"
    DOWNSTREAM_TRANSPORTATION = "下游运输"
    BUSINESS_TRAVEL = "商务差旅"
    WASTE_DISPOSAL = "废弃物处理"


@dataclass
class EmissionFactor:
    name: str
    factor: float
    unit: str
    scope: str
    category: str
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class FieldMapping:
    source_field: str
    target_field: str
    data_type: str = "string"
    required: bool = False


@dataclass
class EmissionRecord:
    id: str = ""
    date: str = ""
    department: str = ""
    source_type: str = ""
    activity_data: float = 0.0
    activity_unit: str = ""
    emission_factor: float = 0.0
    factor_unit: str = ""
    emissions: float = 0.0
    emissions_unit: str = "tCO2e"
    scope: str = ""
    category: str = ""
    product: str = ""
    remarks: str = ""


@dataclass
class ReductionRecord:
    id: str = ""
    date: str = ""
    measure: str = ""
    reduction_amount: float = 0.0
    unit: str = "tCO2e"
    department: str = ""
    description: str = ""


@dataclass
class Target:
    year: int
    scope1_target: float = 0.0
    scope2_target: float = 0.0
    scope3_target: float = 0.0
    total_target: float = 0.0
    unit: str = "tCO2e"
    description: str = ""


@dataclass
class ProductAllocation:
    product: str
    allocation_ratio: float
    department: str = ""
