/**
 * OpsAxiom × Pi 深度整合扩展（N-2）。
 *
 * pi 提供智能入口（模型驱动的对话/编排/多 provider），OpsAxiom 提供"法律"：
 * 决策树、解析器、白名单、审批门。模型能调的只有下面注册的 axiom_* 工具——
 * 工具内部全是确定性引擎（Python 侧 incident/diagnose），模型永远拿不到
 * 出命令/判分支的权力（宪法 R7/R9/R10 在工具边界上成立）。
 *
 * 启动方式（tools/bin/opsaxiom 自动探测，或手动）：
 *   pi -e /path/to/ops-agent/tools/pi/opsaxiom.ts
 * 需要：node >= 22.19 + npm install @earendil-works/pi-coding-agent
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import * as path from "node:path";
import * as fs from "node:fs";
import * as os from "node:os";

// 仓库根：本文件在 <root>/tools/pi/ 下；OPSAXIOM_ROOT 可覆盖
const ROOT =
  process.env.OPSAXIOM_ROOT ||
  path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PY = process.env.OPSAXIOM_PY || "python3";
const CLI = path.join(ROOT, "tools", "bin", "opsaxiom");

function runCli(args: string[], timeoutMs = 120000): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(
      PY,
      [CLI, ...args],
      { timeout: timeoutMs, maxBuffer: 8 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) reject(new Error(String(stderr || err.message).slice(0, 800)));
        else resolve(stdout);
      },
    );
  });
}

const SYSTEM_RULES = `
## OpsAxiom 运维助手守则（不可违反）
你是 OpsAxiom 运维排查助手，面对的是生产环境。
1. 排查一律通过 axiom_* 工具进行：先 axiom_incident 取证出诊断卷宗，再讲结论。
2. 绝不自己编造/建议 shell 命令让用户执行——所有命令只能来自工具返回的已验证 Skill 内容。
3. 转述卷宗时必须保留：证据引用（哪条命令→哪个字段=什么值）、Skill 的成熟度徽章
   （⚪草稿/🔵仿真验证/🟢实地/🟡认证）、以及"已排除/证据不足"的诚实结论。
4. 任何变更（写操作）你无权执行也无权代劳：卷宗给出 treatment 时，引导用户在终端跑
   opsaxiom run <skill-id>（那里有变更简报、审批门、verify 与回滚）。
5. 证据不足就说证据不足，需要什么命令的输出就说清楚。宁可拒绝，不可翻车。
`;

// ---------- 已保存的模型连接（/connect 落盘，重启自动恢复） ----------
const CONNECT_FILE = path.join(
  process.env.OPSAXIOM_HOME || path.join(os.homedir(), ".opsaxiom"),
  "pi-connect.json",
);

type SavedConn = {
  provider: string;          // pi 内的 provider id
  label: string;
  apiKey: string;
  baseUrl?: string;          // 自定义/预置 OpenAI 兼容端点才有
  modelId?: string;          // 自定义 provider 注册的模型
  builtin: boolean;          // true=覆盖 pi 内置 provider；false=新注册
};

function loadConns(): SavedConn[] {
  try {
    return JSON.parse(fs.readFileSync(CONNECT_FILE, "utf-8"));
  } catch {
    return [];
  }
}

function saveConns(conns: SavedConn[]) {
  fs.mkdirSync(path.dirname(CONNECT_FILE), { recursive: true });
  fs.writeFileSync(CONNECT_FILE, JSON.stringify(conns, null, 2), { mode: 0o600 });
}

// 内置服务商 → pi-ai 的环境变量名（env-api-keys.ts 的解析口径）。
// 教训（发起人真机实测）：registerProvider 部分覆盖会抹掉内置 provider 的 baseUrl，
// 之后所有请求打到空地址 → "Connection error."。内置服务商只能走 env 注入 Key。
const BUILTIN_ENV: Record<string, string> = {
  deepseek: "DEEPSEEK_API_KEY",
  anthropic: "ANTHROPIC_API_KEY",
  openai: "OPENAI_API_KEY",
  google: "GEMINI_API_KEY",
  openrouter: "OPENROUTER_API_KEY",
};

function registerConn(pi: ExtensionAPI, c: SavedConn) {
  if (c.builtin) {
    // 不动 provider 定义，只注入 Key（pi-ai 请求时从 env 解析鉴权）
    const env = BUILTIN_ENV[c.provider];
    if (env) process.env[env] = c.apiKey;
  } else {
    pi.registerProvider(c.provider, {
      name: c.label,
      baseUrl: c.baseUrl!,
      apiKey: c.apiKey || "none",
      api: "openai-completions",
      models: [
        {
          id: c.modelId!,
          name: `${c.modelId}（${c.label}）`,
          reasoning: false,
          input: ["text"],
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
          contextWindow: 32768,
          maxTokens: 4096,
        },
      ],
    });
  }
}

// ---------- 卡皮巴拉（发起人钦定吉祥物）+ 欢迎文案 ----------
function capybaraHeader(theme: any): string[] {
  const a = (s: string) => theme.fg("accent", s);   // 轮廓
  const m = (s: string) => theme.fg("muted", s);
  const d = (s: string) => theme.fg("dim", s);
  // 憨厚小卡皮巴拉：顶上小圆耳(∩ ∩)、眯眯眼(-  -)、方吻(ᴥ)、鼓身、四小短腿
  return [
    "",
    `  ${a("   ∩      ∩")}`,
    `  ${a(" (  -    -  )")}      ${a("◆ OpsAxiom")} ${d("× pi")}`,
    `  ${a(" (    ᴥ     )")}      ${m("把运维专家的判断，编译成可回滚的资产")}`,
    `  ${a(" (          )")}      ${m("直接说故障：")}${d("磁盘满了 / xid 79 / kafka 积压")}`,
    `  ${a("  \\________/")}       ${d("/connect 接模型（自己输 Key）· /model 切换")}`,
    `  ${a("   u u  u u")}        ${d("命令与判读永远出自已验证 Skill")}`,
    "",
  ];
}

// ---------- /connect 预置菜单 ----------
// builtin=true：pi 自带模型目录，只需 Key；builtin=false：OpenAI 兼容端点直连
const PROVIDER_PRESETS: Array<{
  label: string; provider: string; builtin: boolean;
  baseUrl?: string; defaultModel?: string; keyHint?: string;
}> = [
  { label: "DeepSeek", provider: "deepseek", builtin: true },
  { label: "Anthropic Claude", provider: "anthropic", builtin: true },
  { label: "OpenAI", provider: "openai", builtin: true },
  { label: "Google Gemini", provider: "google", builtin: true },
  { label: "OpenRouter（一个 Key 通多家）", provider: "openrouter", builtin: true },
  { label: "阿里云百炼（通义千问）", provider: "bailian", builtin: false,
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    defaultModel: "qwen-plus", keyHint: "sk-…（百炼控制台 API-KEY）" },
  { label: "月之暗面 Kimi", provider: "moonshot-cn", builtin: false,
    baseUrl: "https://api.moonshot.cn/v1", defaultModel: "moonshot-v1-8k" },
  { label: "✎ 自定义（自己填 URL / API Key / Model ID）", provider: "custom", builtin: false },
];

export default function (pi: ExtensionAPI) {
  // 启动即恢复已保存连接（Key 存本地 0600 文件，永不入日志）
  for (const c of loadConns()) {
    try {
      registerConn(pi, c);
    } catch {
      /* 单条坏配置不阻塞启动 */
    }
  }

  // ---------- 欢迎界面：卡皮巴拉 ----------
  pi.on("session_start", async (_event, ctx) => {
    if (ctx.mode === "tui") {
      ctx.ui.setHeader((_tui, theme) => ({
        render(_width: number): string[] {
          return capybaraHeader(theme);
        },
        invalidate() {},
      }));
    }

    // 运维态工具面收窄：砍掉写文件/改代码类工具，保留只读 + axiom_*。
    // bash 一并砍掉——排查命令由 Skill 引擎出，不给模型自由 shell（R10）。
    try {
      const all = pi.getAllTools().map((t: any) => t.name ?? t);
      const keep = all.filter(
        (n: string) =>
          n.startsWith("axiom_") || ["read", "grep", "find", "ls"].includes(n),
      );
      pi.setActiveTools(keep);
    } catch {
      /* 工具面收窄失败不阻塞启动 */
    }
  });

  // ---------- 系统提示注入 ----------
  pi.on("before_agent_start", async (event) => {
    return { systemPrompt: event.systemPrompt + "\n" + SYSTEM_RULES };
  });

  // ---------- 本地/常用 provider（发起人点名：本地与远端接入都顺） ----------
  // 内置千问 0.5B：opsaxiom model serve 起的 OpenAI 兼容服务
  pi.registerProvider("opsaxiom-local", {
    name: "OpsAxiom 内置模型（llama.cpp server）",
    baseUrl: process.env.OPSAXIOM_LOCAL_LLM || "http://127.0.0.1:11435/v1",
    apiKey: "none",
    api: "openai-completions",
    models: [
      {
        id: "qwen2.5-0.5b-instruct",
        name: "Qwen2.5 0.5B（内置备用）",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 8192,
        maxTokens: 1024,
      },
    ],
  });
  // 本机 Ollama（OpenAI 兼容 /v1）
  pi.registerProvider("ollama", {
    name: "Ollama（本机）",
    baseUrl: process.env.OLLAMA_HOST_V1 || "http://127.0.0.1:11434/v1",
    apiKey: "none",
    api: "openai-completions",
    models: [
      {
        id: "qwen2.5:7b",
        name: "Qwen2.5 7B (ollama)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 32768,
        maxTokens: 4096,
      },
    ],
  });

  // ---------- 工具 1：候选检索 ----------
  pi.registerTool({
    name: "axiom_diagnose",
    label: "OpsAxiom 匹配 Skill",
    description:
      "把故障症状匹配到 OpsAxiom 已验证 Skill 库，返回候选（含成熟度徽章）。" +
      "轻量检索，不执行任何命令。",
    parameters: Type.Object({
      symptom: Type.String({ description: "故障的自然语言描述" }),
    }),
    async execute(_id, params) {
      const out = await runCli(["diagnose", params.symptom, "--json"], 30000);
      return { content: [{ type: "text", text: out.trim() }], details: {} };
    },
  });

  // ---------- 工具 2：取证式诊断（核心） ----------
  pi.registerTool({
    name: "axiom_incident",
    label: "OpsAxiom 取证诊断",
    description:
      "对故障做取证式诊断：多假设→本机只读批量取证→决策树在事实上干跑→诊断卷宗" +
      "（已证实/已排除/证据不足，每条带证据引用）。只执行白名单只读命令。" +
      "params 传已知实体（如 mount=/data host=web-01）。远端设备用 target=<名字>，" +
      "会返回给人执行的命令清单而不执行。",
    parameters: Type.Object({
      symptom: Type.String({ description: "故障的自然语言描述" }),
      params: Type.Optional(
        Type.Record(Type.String(), Type.String(), {
          description: "已知实体，如 {mount:'/data'}",
        }),
      ),
      target: Type.Optional(
        Type.String({ description: "默认 local（本机）；远端设备填名字" }),
      ),
    }),
    async execute(_id, params, _signal, _onUpdate, ctx) {
      const args = ["incident", params.symptom, "--json"];
      for (const [k, v] of Object.entries(params.params || {}))
        args.push("--param", `${k}=${v}`);
      if (params.target) args.push("--target", params.target);

      let out = JSON.parse(await runCli(args));
      // 本机自动取证需一次性授权：审批走 pi 的 UI（R6 审批门语义）
      if (out.needs_grant) {
        const ok = ctx.hasUI
          ? await ctx.ui.confirm(
              "OpsAxiom 本机取证授权",
              `将自动执行 ${out.auto_count} 条只读命令（均出自已验证 Skill，绝无写操作）。允许？`,
            )
          : false;
        if (!ok)
          return {
            content: [
              { type: "text", text: "用户未授权本机自动取证。可改用远端粘贴块流程。" },
            ],
            details: {},
          };
        out = JSON.parse(await runCli([...args, "--grant"]));
      }
      const text =
        out.dossier_text ||
        out.plan?.paste_block ||
        out.note ||
        JSON.stringify(out).slice(0, 2000);
      return {
        content: [{ type: "text", text }],
        details: {
          dossier: out.dossier ?? null,
          treatment: out.treatment ?? null,
          handover: out.handover ?? null,
        },
      };
    },
  });

  // ---------- 工具 3：故障报告导出 ----------
  pi.registerTool({
    name: "axiom_report",
    label: "OpsAxiom 故障报告",
    description:
      "对某症状重跑取证诊断并导出 markdown 故障报告（可贴工单/移交人工）。",
    parameters: Type.Object({
      symptom: Type.String(),
      params: Type.Optional(Type.Record(Type.String(), Type.String())),
    }),
    async execute(_id, params) {
      const args = ["incident", params.symptom, "--json"];
      for (const [k, v] of Object.entries(params.params || {}))
        args.push("--param", `${k}=${v}`);
      const out = JSON.parse(await runCli(args));
      const md = out.report_markdown || out.note || "（无报告：可能未授权取证）";
      return { content: [{ type: "text", text: md }], details: {} };
    },
  });

  // ---------- 命令：/connect 接模型向导（自己选家、自己输 Key） ----------
  pi.registerCommand("connect", {
    description: "接一个远程/本地模型：选服务商 → 输 API Key → 立即切换",
    handler: async (_args, ctx) => {
      if (!ctx.hasUI) {
        ctx.ui.notify("connect 需要交互终端", "error");
        return;
      }
      const labels = PROVIDER_PRESETS.map((p) => p.label);
      const picked = await ctx.ui.select("接哪家模型？", labels);
      if (picked == null) return;
      const preset = PROVIDER_PRESETS[labels.indexOf(picked)];
      const isCustom = preset.provider === "custom";

      // 自定义：三件套自己填（起个名 → URL → Model ID）
      let label = preset.label;
      let baseUrl = preset.baseUrl;
      if (isCustom) {
        label = (await ctx.ui.input("给这个连接起个名（如 公司网关 / 我的vLLM）:", "自定义")) || "自定义";
        baseUrl = (await ctx.ui.input(
          "Base URL（OpenAI 兼容，须含 /v1，如 https://host/v1）:", "")) || "";
        if (!baseUrl) return;
      }
      // 模型名（自定义/预置 OpenAI 兼容端点需要；内置 provider 用 pi 自带目录）
      let modelId = preset.defaultModel;
      if (!preset.builtin) {
        modelId = (await ctx.ui.input(
          `Model ID${preset.defaultModel ? `（回车用 ${preset.defaultModel}）` : "（如 deepseek-chat / gpt-4o-mini）"}:`,
          preset.defaultModel || "",
        )) || preset.defaultModel;
        if (!modelId) return;
      }
      const apiKey = (await ctx.ui.input(
        `API Key${preset.keyHint ? `（${preset.keyHint}）` : ""}（本机 0600 保存，不上传；无鉴权可留空）:`,
        "",
      )) || "";
      if (preset.builtin && !apiKey) {
        ctx.ui.notify("内置服务商必须有 Key", "error");
        return;
      }

      // provider id：自定义从 host 派生（非法 URL 不崩），其余用预置 id
      let providerId = preset.provider;
      if (isCustom) {
        let host = "endpoint";
        try {
          host = new URL(baseUrl!).hostname.replace(/[^a-z0-9]/gi, "-");
        } catch {
          ctx.ui.notify("Base URL 格式不对（要 http(s)://…/v1）", "error");
          return;
        }
        providerId = `custom-${host}`;
      }
      const conn: SavedConn = {
        provider: providerId, label, apiKey,
        baseUrl, modelId, builtin: preset.builtin,
      };
      try {
        registerConn(pi, conn);
      } catch (e) {
        ctx.ui.notify(`注册失败：${String(e).slice(0, 120)}`, "error");
        return;
      }
      // 持久化（同 provider 覆盖旧条目）
      const conns = loadConns().filter((c) => c.provider !== providerId);
      conns.push(conn);
      saveConns(conns);

      // 立即切换：内置 provider 从 pi 模型目录列出该家模型让用户当场挑；自定义直接上
      if (preset.builtin) {
        const mine = ctx.modelRegistry
          .getAll()
          .filter((mm: any) => mm.provider === providerId);
        if (mine.length) {
          const ids = mine.map((mm: any) => mm.id);
          const pickedModel = await ctx.ui.select(
            `${preset.label} 已接入，选一个模型：`, ids);
          if (pickedModel != null) {
            const model = ctx.modelRegistry.find(providerId, pickedModel);
            if (model && (await pi.setModel(model))) {
              ctx.ui.notify(`已切到 ${preset.label} / ${pickedModel}`, "info");
              return;
            }
          }
        }
        ctx.ui.notify(`${preset.label} 已接入。用 /model 挑一个具体模型。`, "info");
      } else {
        const model = ctx.modelRegistry.find(providerId, modelId!);
        if (model && (await pi.setModel(model))) {
          ctx.ui.notify(`已切到 ${preset.label} / ${modelId}`, "info");
        } else {
          ctx.ui.notify(`已注册但切换失败，用 /model 手动选（检查 Key/端点）`, "warning");
        }
      }
    },
  });

  // ---------- 命令：/axiom 快速状态 ----------
  pi.registerCommand("axiom", {
    description: "OpsAxiom 状态（Skill 库/模型后端）",
    handler: async (_args, ctx) => {
      const out = await runCli(["model", "show"], 30000).catch((e) => String(e));
      ctx.ui.notify("OpsAxiom 就绪。工具：axiom_diagnose / axiom_incident / axiom_report", "info");
      if (ctx.hasUI) ctx.ui.setWidget("axiom-status", out.trim().split("\n").slice(0, 10));
    },
  });
}
