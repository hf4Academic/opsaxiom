"""
localskill.py —— 本地派生 Skill（fork）与"个人层不出门"红线（docs/13 §3-4，I-10）。

fork = 真的要改流程时的私有派生：拷通用 Skill 到 ~/.opsaxiom/skills-local/，
换 local. 前缀 id、写 derived_from 血缘、置 visibility:local、徽章清零(draft)。
本地照常走 validate/sim/promote（本地徽章本地有效）。

出门红线（结构性，双保险 + CI 三保险）：
  is_local(meta) 为真的 Skill —— 打包器(hub_push)拒绝、registry 构建(build_registry)
  拒绝。即便有人把 fork 拷进公共 skills/，构建也会当场报错，出不了门。
"""
import os
import pathlib
import shutil

import yaml

LOCAL_PREFIX = "local."


def _home():
    return pathlib.Path(os.environ.get("OPSAXIOM_HOME", pathlib.Path.home() / ".opsaxiom"))


def skills_local_dir():
    return _home() / "skills-local"


def is_local(meta):
    """个人层判定：id 带 local. 前缀 或 visibility=local。任一为真即不出门。"""
    return (str(meta.get("id", "")).startswith(LOCAL_PREFIX)
            or meta.get("visibility") == "local")


def assert_shareable(meta, where=""):
    """出门前的守卫：个人层 Skill 一律拒绝对外（打包/构建都调它）。"""
    if is_local(meta):
        raise LocalSkillError(
            f"拒绝对外发布个人层 Skill：{meta.get('id')}"
            + (f"（在 {where}）" if where else "")
            + "——local. 前缀 / visibility:local 的派生永不出门（docs/13 §4）")


class LocalSkillError(Exception):
    pass


def fork(base_skill, base_path, base_version="0.1.0"):
    """从通用 Skill 派生本地 fork，写入 skills-local/<new-id>/skill.yaml，返回路径。"""
    base_meta = base_skill["metadata"]
    base_id = base_meta["id"]
    if is_local(base_meta):
        raise LocalSkillError(f"{base_id} 本身就是本地 Skill，不能再 fork")
    # 新 id：local.<原 id 去掉域段重复的简化> —— 直接前缀化，保证唯一且可辨
    new_id = LOCAL_PREFIX + base_id
    new_skill = dict(base_skill)
    m = dict(base_meta)
    m["id"] = new_id
    m["derived_from"] = f"{base_id}@{base_meta.get('version', base_version)}"
    m["visibility"] = "local"
    m["maturity"] = "draft"                     # 改过的树没验证过，徽章清零
    new_skill["metadata"] = m

    dst = skills_local_dir() / new_id
    if dst.exists():
        raise LocalSkillError(f"已存在 fork：{dst}")
    dst.mkdir(parents=True)
    (dst / "skill.yaml").write_text(
        yaml.safe_dump(new_skill, allow_unicode=True, sort_keys=False), encoding="utf-8")
    # 带上 tests 目录（若有），本地流水线要用
    tdir = pathlib.Path(base_path).parent / "tests"
    if tdir.is_dir():
        shutil.copytree(tdir, dst / "tests")
    return dst / "skill.yaml"
