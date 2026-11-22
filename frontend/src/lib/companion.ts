// Client cho companion-api (api-contracts.md §3b, ADR-0016) qua /api/companion/*.
//
// Tien do Capy do BACKEND tinh (companion.service) - frontend chi hien thi,
// KHONG bao gio tu cong/tinh tien do. Response khong co don vi noi bo.

export type CompanionUnavailableReason = "FEATURE_OFF" | "RUNTIME_UNSUPPORTED";

export type CompanionState =
  | { enabled: false; unavailableReason: CompanionUnavailableReason }
  | {
      enabled: true;
      stage: number;
      stageKey: string;
      stageLabel: string;
      nextStageKey: string | null;
      nextStageLabel: string | null;
      isMaxStage: boolean;
      progressPct: number;
      name: string | null;
      pendingCelebrationStage: number | null;
    };

export type CompanionUiEvent =
  "FEED_TAP" | "FEED_AUTO" | "FEED_SKIP" | "SUPPORTIVE_SHOWN" | "GROWTH_SEEN" | "SHEET_OPEN";

type CompanionStateApi = {
  enabled: boolean;
  unavailable_reason: CompanionUnavailableReason | null;
  stage: number | null;
  stage_key: string | null;
  stage_label: string | null;
  next_stage_key: string | null;
  next_stage_label: string | null;
  is_max_stage: boolean | null;
  progress_pct: number | null;
  name: string | null;
  pending_celebration_stage: number | null;
};

function headers(accessToken?: string | null): HeadersInit {
  return {
    "Content-Type": "application/json",
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  };
}

async function docLoi(response: Response, macDinh: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // khong phai JSON
  }
  return macDinh;
}

export function toCompanionState(d: CompanionStateApi): CompanionState {
  if (!d.enabled || d.stage == null) {
    return { enabled: false, unavailableReason: d.unavailable_reason ?? "FEATURE_OFF" };
  }
  return {
    enabled: true,
    stage: d.stage,
    stageKey: d.stage_key ?? "",
    stageLabel: d.stage_label ?? "",
    nextStageKey: d.next_stage_key,
    nextStageLabel: d.next_stage_label,
    isMaxStage: Boolean(d.is_max_stage),
    progressPct: Math.max(0, Math.min(100, d.progress_pct ?? 0)),
    name: d.name,
    pendingCelebrationStage: d.pending_celebration_stage,
  };
}

/** GET /companion/me - doc thuan. Throw khi loi mang/HTTP (nguoi goi tu an fallback). */
export async function getCompanion(accessToken?: string | null): Promise<CompanionState> {
  const response = await fetch("/api/companion/me", {
    headers: headers(accessToken),
    cache: "no-store",
  });
  if (!response.ok) throw new Error(await docLoi(response, "Không tải được Capy"));
  return toCompanionState(await response.json());
}

export async function renameCompanion(
  name: string,
  accessToken?: string | null,
): Promise<CompanionState> {
  const response = await fetch("/api/companion/me", {
    method: "PATCH",
    headers: headers(accessToken),
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error(await docLoi(response, "Không đặt được tên cho Capy"));
  return toCompanionState(await response.json());
}

/** Ack le lon len - idempotent o backend (goi lai van 204). */
export async function ackCelebration(stage: number, accessToken?: string | null): Promise<boolean> {
  const response = await fetch(`/api/companion/me/celebrations/${stage}/ack`, {
    method: "POST",
    headers: headers(accessToken),
  });
  return response.status === 204;
}

/** Event do luong UI - fire-and-forget, KHONG BAO GIO throw. */
export function sendCompanionEvent(event: CompanionUiEvent, accessToken?: string | null): void {
  void fetch("/api/companion/me/events", {
    method: "POST",
    headers: headers(accessToken),
    body: JSON.stringify({ event }),
    keepalive: true,
  }).catch(() => undefined);
}
