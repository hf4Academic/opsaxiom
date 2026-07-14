"""SMART 解析器（G-3）——磁盘健康预警诊断。

health-v1：smartctl -H（可多盘）→ rows[{dev, passed}] + failed_count。
attrs-v1：smartctl -A → 关键属性标量。SATA 与 NVMe 字段名不同，两者都认：
  SATA:  Reallocated_Sector_Ct / Current_Pending_Sector / Offline_Uncorrectable / UDMA_CRC_Error_Count
  NVMe:  Media_and_Data_Integrity_Errors（→uncorrectable）/ Percentage_Used
领域知识落在解析器契约上：crc_errors 单列出来，是为了让判据能区分"线缆/接口问题"与"盘坏"。
"""
import re


def parse_health(text):
    """smartctl -H 输出（一段或多盘拼接）。认 'result: PASSED/FAILED' 与
    可选前缀 '<dev>:'。行内无 dev 时用序号占位。"""
    rows = []
    cur_dev = ""
    for line in (text or "").splitlines():
        dm = re.match(r"^\s*(/dev/\S+)\s*:", line)
        if dm:
            cur_dev = dm.group(1)
        m = re.search(r"self-assessment test result:\s*(\w+)", line) or \
            re.search(r"SMART Health Status:\s*(\w+)", line)          # NVMe 措辞
        if m:
            passed = m.group(1).upper() in ("PASSED", "OK")
            rows.append({"dev": cur_dev or f"disk{len(rows)}",
                         "passed": 1 if passed else 0})
    failed = sum(1 for r in rows if not r["passed"])
    return {"rows": rows, "output": {"disk_count": len(rows), "failed_count": failed}}


_ATTR = {
    "reallocated": ["Reallocated_Sector_Ct"],
    "pending": ["Current_Pending_Sector"],
    "uncorrectable": ["Offline_Uncorrectable", "Media_and_Data_Integrity_Errors"],
    "crc_errors": ["UDMA_CRC_Error_Count"],
}


def parse_attrs(text):
    """smartctl -A → reallocated/pending/uncorrectable/crc_errors（取 RAW_VALUE 末列）。"""
    out = {"reallocated": 0, "pending": 0, "uncorrectable": 0, "crc_errors": 0}
    for line in (text or "").splitlines():
        for key, names in _ATTR.items():
            for nm in names:
                if nm in line:
                    m = re.search(r":\s*([\d,]+)", line) or \
                        re.search(r"(\d+)\s*$", line.strip())
                    if m:
                        try:
                            out[key] = max(out[key], int(m.group(1).replace(",", "")))
                        except ValueError:
                            pass
    return {"output": out}


def install(register):
    register("smart/health-v1", parse_health,
             {"rows": ["dev", "passed"], "scalars": ["disk_count", "failed_count"],
              "lines": False})
    register("smart/attrs-v1", parse_attrs,
             {"scalars": ["reallocated", "pending", "uncorrectable", "crc_errors"],
              "lines": False})
