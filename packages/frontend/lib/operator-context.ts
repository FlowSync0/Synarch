const DEFAULT_OPERATOR_ID = "local-user";
const OPERATOR_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,119}$/;

export function getOperatorId(): string {
  const configured = process.env.NEXT_PUBLIC_SYNARCH_OPERATOR_ID?.trim();
  if (configured && OPERATOR_ID_PATTERN.test(configured)) {
    return configured;
  }
  return DEFAULT_OPERATOR_ID;
}

export function operatorHeaders(traceId?: string): Record<string, string> {
  return {
    "X-Synarch-Actor-Type": "user",
    "X-Synarch-Actor-Id": getOperatorId(),
    ...(traceId ? { "X-Synarch-Trace-Id": traceId } : {})
  };
}

export function operatorJsonHeaders(traceId?: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    ...operatorHeaders(traceId)
  };
}
