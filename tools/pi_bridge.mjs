#!/usr/bin/env node
/**
 * pi_bridge.mjs —— OpsAxiom → Pi Agent Harness 的多 provider 桥（M-3）。
 *
 * stdin 读一个 JSON：{provider, model, endpoint?, apiKey?, system, prompt, maxTokens?}
 * stdout 写一个 JSON：{text} 或 {error}
 *
 * 依赖 @earendil-works/pi-ai（node >= 22.19）：
 *   npm install @earendil-works/pi-ai        # 在 tools/ 或全局
 * 不满足时本脚本以非零退出，llm.py 侧按约定降级（宁可拒绝，不可翻车 R10）。
 *
 * 边界：桥只做"一问一答文本补全"——OpsAxiom 的 LLM 适配层三调用点只需要这个；
 * 不透传工具调用（判读/命令永远不走模型，宪法 R7/R9/R10）。
 */

async function main() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  const req = JSON.parse(Buffer.concat(chunks).toString("utf-8"));

  const { builtinModels } = await import("@earendil-works/pi-ai/providers/all");

  // apiKey 优先显式传入；否则走 pi-ai 自己的 env 解析（OPENAI_API_KEY 等）
  if (req.apiKey) {
    const envKey = `${String(req.provider || "openai").toUpperCase().replace(/-/g, "_")}_API_KEY`;
    process.env[envKey] = req.apiKey;
  }

  const models = builtinModels();
  const model = models.getModel(req.provider || "openai", req.model);
  if (!model) {
    process.stdout.write(JSON.stringify({
      error: `unknown model ${req.provider}/${req.model}` }));
    process.exit(3);
  }

  const context = {
    systemPrompt: req.system || "",
    messages: [{ role: "user", content: req.prompt || "", timestamp: Date.now() }],
    tools: [],
  };

  let text = "";
  const s = models.stream(model, context, { maxTokens: req.maxTokens || 512 });
  for await (const ev of s) {
    if (ev.type === "text_delta") text += ev.delta;
    if (ev.type === "error") {
      process.stdout.write(JSON.stringify({ error: String(ev.error || "stream error") }));
      process.exit(4);
    }
  }
  process.stdout.write(JSON.stringify({ text }));
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ error: String(e && e.message || e) }));
  process.exit(2);
});
