"""GPU 驱动/CUDA 解析器（G-5）——驱动/CUDA 不匹配诊断。

nvml-v1：nvidia-smi 是否通 + 是否报 mismatch。
driver-versions-v1：内核模块版本 vs 用户态包版本是否一致。
cuda-compat-v1：CUDA 运行时版本对宿主驱动是否兼容——内置 CUDA↔最低驱动对照表
  （Fable 已核对，照抄勿改；来源 NVIDIA CUDA Release Notes 的 minimum required driver）。
"""
import re

# CUDA 版本 → Linux 上该 CUDA 所需的最低驱动版本（>= 即兼容）。
_CUDA_MIN_DRIVER = {
    "12.6": 560.28, "12.5": 555.42, "12.4": 550.54, "12.3": 545.23,
    "12.2": 535.54, "12.1": 530.30, "12.0": 525.60,
    "11.8": 450.80, "11.7": 450.80, "11.6": 450.80, "11.4": 450.80,
    "11.2": 450.80, "11.0": 450.36,
}


def parse_nvml(text):
    """nvidia-smi 输出头几行 → nvml_ok / mismatch_hint。"""
    t = text or ""
    mismatch = 1 if re.search(r"[Dd]river/library version mismatch", t) else 0
    # 正常输出含表头 'NVIDIA-SMI' 且无 mismatch/Failed
    ok = 1 if ("NVIDIA-SMI" in t and not mismatch
               and "Failed to initialize NVML" not in t) else 0
    return {"output": {"nvml_ok": ok, "mismatch_hint": mismatch}}


def parse_driver_versions(text):
    """/proc/driver/nvidia/version（内核模块）+ 包管理器版本 → 是否一致。
    宽松取形如 550.54.15 / 535.104.05 的版本号，比较主.次段。"""
    vers = re.findall(r"\b(\d{3}\.\d{2,3}(?:\.\d+)?)\b", text or "")
    kernel = vers[0] if vers else ""
    userland = vers[1] if len(vers) > 1 else ""

    def mm(v):
        p = v.split(".")
        return ".".join(p[:2]) if len(p) >= 2 else v
    same = 1 if kernel and userland and mm(kernel) == mm(userland) else 0
    return {"output": {"kernel_mod_ver": kernel, "userland_ver": userland,
                       "same_ver": same}}


def parse_cuda_compat(text):
    """driver_version（nvidia-smi）+ cuda_version（nvcc）→ compat_ok（查对照表）。"""
    drivers = re.findall(r"\b(\d{3}\.\d{2,3})", text or "")
    try:
        driver_num = float(drivers[0]) if drivers else 0.0
    except ValueError:
        driver_num = 0.0
    cm = re.search(r"release\s+(\d+\.\d+)", text or "") or \
        re.search(r"[Cc]uda[_ ]?(?:version)?[:\s]+(\d+\.\d+)", text or "")
    cuda_ver = cm.group(1) if cm else ""
    min_drv = _CUDA_MIN_DRIVER.get(cuda_ver)
    if min_drv is None or driver_num == 0.0:
        compat = 1                       # 未知 CUDA 或读不到驱动 → 不武断判失败
    else:
        compat = 1 if driver_num >= min_drv else 0
    return {"output": {"driver_ver": driver_num, "cuda_ver": cuda_ver,
                       "min_driver": min_drv or 0.0, "compat_ok": compat}}


def install(register):
    register("gpu/nvml-v1", parse_nvml,
             {"scalars": ["nvml_ok", "mismatch_hint"]})
    register("gpu/driver-versions-v1", parse_driver_versions,
             {"scalars": ["kernel_mod_ver", "userland_ver", "same_ver"]})
    register("gpu/cuda-compat-v1", parse_cuda_compat,
             {"scalars": ["driver_ver", "cuda_ver", "min_driver", "compat_ok"]})
