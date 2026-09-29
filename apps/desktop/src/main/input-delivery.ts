export type DeliveryPorts = {
  deliver: (target: string, text: string) => Promise<void>;
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
  try {
    await ports.deliver(target, text);
    return {
      status: "paste-requested" as const,
      reason: "已发送粘贴，请检查输入框；最近结果保留了副本。",
    };
  } catch (error) {
    return {
      status: "ready-to-copy" as const,
      reason: error instanceof Error ? error.message : String(error),
    };
  }
}
