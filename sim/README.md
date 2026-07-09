# 仿真验证环境 v0（O-6）

> 目的：让 Skill 从 `draft` 晋级 `sim_verified` 有据可依（docs/05 §1）——
> 决策树逻辑能回归、回滚往返能实测。本轮无需 docker/root，纯本地沙箱。

## 组成

- `run_sim.py` —— 执行器：用真实的表达式求值器（`tools/exprlang.evaluate`）驱动 Skill 决策树，
  按场景提供的每节点上下文选分支，断言实际路径 == `expect_path`；对标注 `real_action` 的
  action 节点真实执行回滚往返（当前支持 `opsaxiom-quarantine` 的 move→restore）。
- `scenarios/*.yaml` —— 故障场景。当前覆盖金标准 disk-full 的三条测试路径。

## 运行

```bash
python3 sim/run_sim.py sim/scenarios/disk-full-inode-exhaustion.yaml
# 或跑全部（含回滚往返）：
python3 -m pytest tools/tests/test_sim.py -q
```

## 场景格式

```yaml
skill: skills/host/disk-full/skill.yaml        # 被测 Skill
scenario: 人类可读描述
expect_path: [node1, node2, ...]               # 期望走过的节点序列
answers: {ask_node_id: chosen_goto}            # 模拟人在 ask 节点的选择
real_action: quarantine_files                  # 可选：对该 action 做真实回滚往返验证
sandbox_file: victim.dat                        # 真实回滚验证用的沙箱文件名
node_ctx:                                       # 每个 check 节点的上下文（= 解析器产物的模拟）
  node_id: {rows: [...], output: {...}, ...}
```

## v0 边界与后续

- check 节点的输出由场景直接给出结构化上下文（相当于解析器产物），尚未接真实靶机命令执行。
  → 下一轮：Docker 靶机 + 真实命令 + 真实解析器串联。
- action 节点仅对 quarantine 类做了真实回滚往返；service_restore / transaction 型回滚
  （reload、rollout undo）本轮为路径级验证。→ 下一轮：容器内真实执行。
- 网络设备仿真（containerlab + cEOS/vrnetlab）未做。→ 下一轮：为 bgp 金标准补真实设备仿真。
- 已实现的确定性资产（求值器、quarantine 工具、语法树）均可直接复用到真实靶机执行器。
