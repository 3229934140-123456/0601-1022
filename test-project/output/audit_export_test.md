# 数据处理历史 (最近 5 条)

**记录数:** 5
**时间范围:** 2026-06-08T15:36:59 ~ 2026-06-08T15:38:47

---

## 1. import.apply

- **ID:** ca6dc639-870
- **时间:** 2026-06-08T15:36:59
- **状态:** success
- **说明:** 应用9个字段映射
- **行数:** 3
- **总排放量:** 0.00 tCO2e

### 输入文件

- `test_manual_raw.csv`

### 输出文件

- `test_manual_mapped.csv`

### 命令参数

- **input:** test_manual_raw.csv
- **output:** test_manual_mapped.csv
- **mappings:** 9

---

## 2. calc.run

- **ID:** b2548266-e9c
- **时间:** 2026-06-08T15:37:01
- **状态:** success
- **说明:** 计算3条（共3条），总排放2,759.78 tCO2e
- **行数:** 3
- **总排放量:** 2,759.78 tCO2e

### 输入文件

- `test_manual_mapped.csv`

### 输出文件

- `test_manual_calc.csv`

### 命令参数

- **input:** test_manual_mapped.csv
- **output:** test_manual_calc.csv
- **unit_check:** True
- **tags:** {'region': '华东', 'year': '2022'}
- **factor_mode:** best
- **total_rows:** 3
- **calculated_rows:** 3

---

## 3. import.apply

- **ID:** 5311d407-90f
- **时间:** 2026-06-08T15:37:19
- **状态:** success
- **说明:** 应用7个字段映射
- **行数:** 3
- **总排放量:** 0.00 tCO2e

### 输入文件

- `test_bilingual.csv`

### 输出文件

- `test_bilingual_mapped.csv`

### 命令参数

- **input:** test_bilingual.csv
- **output:** test_bilingual_mapped.csv
- **mappings:** 7

---

## 4. import.apply

- **ID:** 505e18a8-ebb
- **时间:** 2026-06-08T15:38:20
- **状态:** success
- **说明:** 应用7个字段映射
- **行数:** 3
- **总排放量:** 0.00 tCO2e

### 输入文件

- `test_bilingual.csv`

### 输出文件

- `test_bilingual_mapped2.csv`

### 命令参数

- **input:** test_bilingual.csv
- **output:** test_bilingual_mapped2.csv
- **mappings:** 7

---

## 5. import.apply

- **ID:** 697c5152-5f7
- **时间:** 2026-06-08T15:38:47
- **状态:** success
- **说明:** 应用7个字段映射
- **行数:** 3
- **总排放量:** 0.00 tCO2e

### 输入文件

- `test_bilingual.csv`

### 输出文件

- `test_bilingual_mapped2.csv`

### 命令参数

- **input:** test_bilingual.csv
- **output:** test_bilingual_mapped2.csv
- **mappings:** 7

---
