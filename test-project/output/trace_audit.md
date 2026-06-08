# 数据链路追溯: trace_calc.csv

**记录数:** 3
**时间范围:** 2026-06-08T15:40:00 ~ 2026-06-08T15:40:01

---

## 1. import.file

- **ID:** accae6a8-ae1
- **时间:** 2026-06-08T15:40:00
- **状态:** success
- **说明:** 导入3行数据
- **行数:** 3
- **总排放量:** 0.00 tCO2e

### 输入文件

- `test_manual_raw.csv`

### 输出文件

- `trace_raw.csv`

### 命令参数

- **input_file:** test_manual_raw.csv
- **output_file:** trace_raw.csv
- **sheet:** 
- **append:** False
- **total_rows:** 3
- **existing_rows:** 0
- **new_rows:** 3

---

## 2. calc.run

- **ID:** 4bd17185-16b
- **时间:** 2026-06-08T15:40:01
- **状态:** success
- **说明:** 计算3条（共3条），总排放2,759.78 tCO2e
- **行数:** 3
- **总排放量:** 2,759.78 tCO2e

### 输入文件

- `trace_mapped.csv`

### 输出文件

- `trace_calc.csv`

### 命令参数

- **input:** trace_mapped.csv
- **output:** trace_calc.csv
- **unit_check:** True
- **tags:** {'region': '华东', 'year': '2022'}
- **factor_mode:** best
- **total_rows:** 3
- **calculated_rows:** 3

---

## 3. import.apply

- **ID:** 25aaa820-7dc
- **时间:** 2026-06-08T15:40:01
- **状态:** success
- **说明:** 应用9个字段映射
- **行数:** 3
- **总排放量:** 0.00 tCO2e

### 输入文件

- `trace_raw.csv`

### 输出文件

- `trace_mapped.csv`

### 命令参数

- **input:** trace_raw.csv
- **output:** trace_mapped.csv
- **mappings:** 9

---

## 原始数据来源

- `test_manual_raw.csv`
