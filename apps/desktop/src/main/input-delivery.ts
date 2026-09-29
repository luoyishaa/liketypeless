export type DeliveryPorts = {
  focus: (target: string) => Promise<void>;
  begin: (text: string) => Promise<string>;
  paste: (target: string, lease: string) => Promise<void>;
  restore: (lease: string) => Promise<void>;
};

// The caller persists the result before asking this adapter to deliver it.
export async function deliverText(
  text: string,
  target: string | null,
  ports: DeliveryPorts,
) {
  if (!target)
    return {
      status: "ready-to-copy" as const,
      reason: "文字已保存，请复制到需要的位置。",
    };
  let lease: string | null = null;
  try {
    await ports.focus(target);
    lease = await ports.begin(text);
    await ports.paste(target, lease);
    return {
      status: "paste-requested" as const,
      reason: "已发送粘贴，请检查输入框；最近结果保留了副本。",
    };
  } catch (error) {
    return {
      status: "ready-to-copy" as const,
      reason: error instanceof Error ? error.message : String(error),
    };
  } finally {
    if (lease) await ports.restore(lease);
  }
}
