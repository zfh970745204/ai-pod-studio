export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  retryAfter?: number;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(url, { ...init, headers });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      code?: string;
      message?: string;
      request_id?: string;
      detail?: string | { message?: string };
    };
    const detail = typeof payload.detail === "string" ? payload.detail : payload.detail?.message;
    const error = new ApiError(
      response.status,
      payload.code || `HTTP_${response.status}`,
      payload.message || detail || `请求失败（${response.status}）`,
      payload.request_id,
    );
    const retryAfter = Number(response.headers.get("Retry-After"));
    if (Number.isFinite(retryAfter) && retryAfter > 0) error.retryAfter = retryAfter;
    throw error;
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface UserSummary {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  avatar_asset_id: string | null;
  status: string;
}

export interface UserPreferences {
  user_id: string;
  theme: "light" | "dark" | "system";
  locale: "zh-CN" | "en-US";
  studio_layout: {
    nav_collapsed?: boolean;
    asset_view?: "grid" | "list";
    panel_position?: "right" | "bottom";
    panel_width?: number;
    canvas_fit?: "contain" | "actual";
    last_tool?: string;
    print_output_mode?: "transparent" | "opaque";
  };
  notification_preferences: Record<string, boolean>;
  updated_at: string;
}

export interface BootstrapData {
  user: UserSummary;
  permissions: string[];
  membership: {
    id: string;
    status: string;
    starts_at: string;
    ends_at: string | null;
    plan: { id: string; code: string; name: string; level: number };
    entitlements: {
      discount_bps: number;
      max_concurrent_jobs: number;
      max_upload_mb: number;
      max_image_megapixels: number;
      retention_days: number;
      periodic_points: number;
      extra: Record<string, unknown>;
    };
  };
  points: {
    balance: number;
    status: string;
    lifetime_earned: number;
    lifetime_spent: number;
  };
  service: {
    status: string;
    features: Record<string, boolean>;
  };
  notifications: { unread_count: number };
  preferences: UserPreferences;
}

export interface UserNotification {
  id: string;
  type: string;
  title: string;
  body: string;
  target_url: string | null;
  read_at: string | null;
  created_at: string;
}

export interface PriceRule {
  parameter: string; type: "choice" | "per_unit";
  points: Record<string, number> | number; included?: number; unit?: number;
}

export interface Operation {
  id: string;
  code: string;
  name: string;
  engine_type: string;
  enabled: boolean;
  member_base_points?: number;
  ecommerce_plan?: { version: string; shots: { code: string; label: string; description: string }[] };
  current_price: { base_points: number; parameter_rules?: { rules?: PriceRule[] } } | null;
}

export interface Quote {
  id: string;
  operation_code: string;
  source_asset_id: string | null;
  base_points: number;
  discount_points: number;
  surcharge_points: number;
  final_points: number;
  expires_at: string;
}

export interface ImageJob {
  id: string;
  operation_code: string;
  source_asset_id: string | null;
  output_asset_id: string | null;
  output_asset_ids?: string[];
  status: string;
  refund_status: string;
  parameters: Record<string, unknown>;
  charged_points: number;
  attempt_count: number;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  queued_at: string;
  started_at: string | null;
  completed_at: string | null;
  refunded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Asset {
  id: string;
  root_asset_id: string;
  parent_asset_id: string | null;
  source_job_id: string | null;
  kind: string;
  operation_code: string;
  original_filename: string | null;
  mime_type: string;
  extension: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  has_alpha: boolean | null;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CropOptions { x: number; y: number; width: number; height: number; shape: "rectangle" | "circle" }

export interface SelectionContext {
  width: number;
  height: number;
  restore_limited: boolean;
  has_initial_selection: boolean;
  source_url: string;
  result_url: string;
}

export async function selectionPixels(url: string, signal: AbortSignal) {
  const response = await fetch(url, { signal, credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.message || "修边图片读取失败，请重试");
  }
  return response.blob();
}

export interface PointTransaction {
  id: string;
  entry_type: string;
  delta: number;
  balance_before: number;
  balance_after: number;
  reference_type: string;
  reference_id: string;
  description: string;
  created_at: string;
}

export interface MembershipPlan {
  id: string;
  code: string;
  name: string;
  description: string;
  level: number;
  periodic_points: number;
  operation_discount_bps: number;
  max_concurrent_jobs: number;
  max_upload_mb: number;
  max_image_megapixels: number;
  asset_retention_days: number;
  entitlements: Record<string, unknown>;
}

export interface SessionInfo {
  id: string;
  user_agent: string;
  last_seen_at: string;
  created_at: string;
  expires_at: string;
  current: boolean;
}

export interface PodBlankReference {
  id: string;
  asset_id: string;
  reference_role: "primary" | "detail" | "lifestyle";
  sort_order: number;
  is_supplier_reference: boolean;
  created_at: string;
}

export interface PodBlank {
  id: string;
  name: string;
  category: string;
  material: string;
  confirmed_attributes: Record<string, unknown>;
  suggested_attributes: Record<string, unknown>;
  product_visual_style: Record<string, unknown>;
  status: "active" | "archived";
  references: PodBlankReference[];
  created_at: string;
  updated_at: string;
}

export interface PodProject {
  id: string;
  blank_id: string;
  name: string;
  status: string;
  current_stage: string;
  created_at: string;
  updated_at: string;
}

export interface PodIdea {
  id: string;
  project_id: string;
  generation_job_id: string | null;
  generation_batch_id: string;
  idea_name: string;
  target_audience: string;
  use_case: string;
  emotional_angle: string;
  design_theme: string;
  visual_direction: string;
  recommended_style: string;
  composition_direction: string;
  color_direction: string;
  core_elements: string[];
  avoid_elements: string[];
  rationale: string;
  infringement_risk: { risk_level?: string; warnings?: string[]; [key: string]: unknown };
  status: "proposed" | "adopted" | "archived";
  created_at: string;
  updated_at: string;
}

export interface PodDesignConcept {
  id: string;
  product_idea_id: string;
  generation_job_id: string | null;
  design_name: string;
  visual_style: string;
  composition: string;
  layout: string;
  main_subject: string;
  secondary_elements: string[];
  color_palette: string;
  typography_direction: string;
  pattern_structure: string;
  print_method: string;
  recommended_print_area: string;
  texture_direction: string;
  background_direction: string;
  negative_elements: string[];
  design_prompt: string;
  status: "proposed" | "adopted" | "archived";
  created_at: string;
  updated_at: string;
}

export interface PodPrintCandidate {
  id: string;
  design_concept_id: string;
  asset_id: string;
  generation_job_id: string;
  status: "generated" | "approved" | "rejected";
  created_at: string;
}

export interface PodPrintMaster {
  id: string;
  project_id: string;
  print_candidate_id: string;
  asset_id: string;
  version: number;
  status: "active" | "superseded";
  locked_by: string;
  locked_at: string;
}

export interface PodProduct {
  id: string;
  project_id: string;
  product_idea_id: string;
  design_concept_id: string;
  print_master_id: string;
  primary_visual_asset_id: string | null;
  primary_visual_job_id: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface PodProductCopy {
  id: string;
  product_id: string;
  generation_job_id: string | null;
  version: number;
  locale: string;
  product_title: string;
  product_description: string;
  selling_points: string[];
  search_keywords: string[];
  content_warnings: string[];
  prompt_snapshot: Record<string, unknown>;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface PodImageSlot {
  id: string;
  image_set_id: string;
  code: string;
  title: string;
  scope: "product_specific" | "generic";
  requires_print: boolean;
  scene_prompt: string;
  composition_prompt: string;
  style_prompt: string;
  sort_order: number;
  asset_id: string | null;
  generation_job_id: string | null;
  prompt_snapshot: Record<string, unknown>;
  status: "planned" | "generated" | "approved" | "rejected";
  created_at: string;
  updated_at: string;
}

export interface PodImageSet {
  id: string;
  product_id: string;
  generation_job_id: string | null;
  version: number;
  strategy_snapshot: { rationale?: string; slots?: unknown[]; [key: string]: unknown };
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
  slots: PodImageSlot[];
}

export interface PodProjectDetail {
  project: PodProject;
  blank: PodBlank;
  ideas: PodIdea[];
  design_concepts: PodDesignConcept[];
  print_candidates: PodPrintCandidate[];
  print_master: PodPrintMaster | null;
  products: PodProduct[];
  image_sets: PodImageSet[];
  product_copies: PodProductCopy[];
}

export interface PageOptions { cursor?: string | null; limit?: number; [key: string]: string | number | null | undefined }
function pageQuery(options: PageOptions = {}) {
  return new URLSearchParams(Object.entries({ limit: 100, ...options }).filter(([, value]) => value !== null && value !== undefined && value !== "").map(([key, value]) => [key, String(value)])).toString();
}

export function estimatedPoints(operation: Operation | undefined, parameters: Record<string, unknown>): number | null {
  if (!operation?.current_price) return null;
  let total = operation.member_base_points ?? operation.current_price.base_points;
  for (const rule of operation.current_price.parameter_rules?.rules || []) {
    const value = parameters[rule.parameter];
    if (value === undefined) continue;
    if (rule.type === "choice" && typeof rule.points === "object") total += rule.points[String(value)] || 0;
    else if (rule.type === "per_unit" && typeof rule.points === "number") total += Math.ceil(Math.max(0, Number(value) - (rule.included || 0)) / (rule.unit || 1)) * rule.points;
  }
  return total * (operation.code === "ai.ecommerce" ? Number(parameters.image_count || 1) : 1);
}

export const jobOutputIds = (job: ImageJob) => job.output_asset_ids?.length ? job.output_asset_ids : job.output_asset_id ? [job.output_asset_id] : [];

export async function downloadJob(jobId: string) {
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}/download`);
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(payload.message || "整组下载失败，请重试"); }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = `studio-${jobId}.zip`; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export const api = {
  currentUser: () => request<{ user: UserSummary }>("/api/v1/auth/me"),
  authOptions: () => request<{ registration_enabled: boolean }>("/api/v1/auth/options"),
  sendRegistrationCode: (email: string) => request<{ status: string; retry_after_seconds: number; expires_in_seconds: number }>("/api/v1/auth/register/email-code", {
    method: "POST", body: JSON.stringify({ email }),
  }),
  register: (email: string, display_name: string, password: string, verification_code: string) =>
    request<{ user: UserSummary }>("/api/v1/auth/register", {
      method: "POST", body: JSON.stringify({ email, display_name, password, verification_code }),
    }),
  login: (identifier: string, password: string) =>
    request<{ user: UserSummary }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  forgotPassword: (identifier: string) =>
    request<{ status: string }>("/api/v1/auth/password/forgot", {
      method: "POST",
      body: JSON.stringify({ identifier }),
    }),
  bootstrap: () => request<BootstrapData>("/api/v1/app/bootstrap"),
  updateProfile: (payload: { display_name: string; username: string | null }) =>
    request<{ user: UserSummary }>("/api/v1/auth/me", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/api/v1/auth/password/change", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),
  sessions: () =>
    request<{ items: SessionInfo[]; recent_failed_logins: unknown[] }>(
      "/api/v1/auth/sessions",
    ),
  revokeSession: (id: string) =>
    request<void>(`/api/v1/auth/sessions/${id}`, { method: "DELETE" }),
  preferences: () => request<{ preferences: UserPreferences }>("/api/v1/me/preferences"),
  updatePreferences: (payload: Record<string, unknown>) =>
    request<{ preferences: UserPreferences }>("/api/v1/me/preferences", {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  notifications: (unreadOnly = false) =>
    request<{ items: UserNotification[]; next_cursor: string | null }>(
      `/api/v1/me/notifications?limit=30&unread_only=${unreadOnly}`,
    ),
  readNotification: (id: string) =>
    request<{ notification: UserNotification }>(`/api/v1/me/notifications/${id}/read`, {
      method: "POST",
    }),
  readAllNotifications: () =>
    request<{ updated: number }>("/api/v1/me/notifications/read-all", { method: "POST" }),
  operations: () => request<{ items: Operation[] }>("/api/v1/operations"),
  quote: (operation_code: string, source_asset_id: string | null, parameters: Record<string, unknown>) =>
    request<{ quote: Quote }>("/api/v1/jobs/quote", {
      method: "POST",
      body: JSON.stringify({ operation_code, source_asset_id, parameters }),
    }),
  createJob: (quote_id: string, parameters: Record<string, unknown>) =>
    request<{ job: ImageJob; created: boolean; dispatched: boolean }>("/api/v1/jobs", {
      method: "POST",
      headers: { "Idempotency-Key": `studio:${quote_id}` },
      body: JSON.stringify({ quote_id, parameters }),
    }),
  jobs: (status = "", page: PageOptions = {}) =>
    request<{ items: ImageJob[]; next_cursor: string | null }>(
      `/api/v1/jobs?${pageQuery({ ...page, status })}`,
    ),
  job: (id: string) => request<{ job: ImageJob }>(`/api/v1/jobs/${id}`),
  jobEvents: (id: string) =>
    request<{ job: ImageJob; next_poll_after_ms: number | null }>(`/api/v1/jobs/${id}/events`),
  cancelJob: (id: string) =>
    request<{ job: ImageJob }>(`/api/v1/jobs/${id}/cancel`, { method: "POST" }),
  assets: (kind = "", page: PageOptions = {}) =>
    request<{ items: Asset[]; next_cursor: string | null }>(
      `/api/v1/assets?${pageQuery({ ...page, kind })}`,
    ),
  asset: (id: string) => request<{ asset: Asset }>(`/api/v1/assets/${id}`),
  selection: (id: string, signal?: AbortSignal) => request<SelectionContext>(`/api/v1/assets/${id}/selection`, { signal }),
  crop: (id: string, options: CropOptions) => request<{ asset: Asset }>(`/api/v1/assets/${id}/crop`, { method: "POST", body: JSON.stringify(options) }),
  saveSelection: (id: string, image: Blob) => {
    const body = new FormData();
    body.append("image", image, "selection-refined.png");
    return request<{ asset: Asset }>(`/api/v1/assets/${id}/selection`, { method: "POST", body });
  },
  saveRasterEdit: (id: string, image: Blob, project?: Blob) => {
    const body = new FormData();
    body.append("image", image, "image-edited.png");
    if (project) body.append("project", project, "layers.raster");
    return request<{ asset: Asset }>(`/api/v1/assets/${id}/edit`, { method: "POST", body });
  },
  printBackground: (id: string, point?: { x: number; y: number }) =>
    request<{ color: string; confidence: number; method: string }>(`/api/v1/assets/${id}/print-background${point ? `?x=${point.x}&y=${point.y}` : ""}`),
  lineage: (id: string) => request<{ items: Asset[] }>(`/api/v1/assets/${id}/lineage`),
  uploadAsset: (file: File, kind = "original") => {
    const body = new FormData();
    body.append("image", file);
    body.append("kind", kind);
    return request<{ asset: Asset }>("/api/v1/assets/upload", { method: "POST", body });
  },
  downloadUrl: (id: string) =>
    request<{ url: string; expires_at: string }>(`/api/v1/assets/${id}/download-url`, {
      method: "POST",
    }),
  deleteAsset: (id: string) =>
    request<{ asset: Asset }>(`/api/v1/assets/${id}`, { method: "DELETE" }),
  pointBalance: () =>
    request<{
      account: {
        balance: number;
        lifetime_earned: number;
        lifetime_spent: number;
        status: string;
      };
    }>("/api/v1/points/balance"),
  pointTransactions: (page: PageOptions = {}) =>
    request<{ items: PointTransaction[]; next_cursor: string | null }>(
      `/api/v1/points/transactions?${pageQuery(page)}`,
    ),
  membership: () => request<{ membership: BootstrapData["membership"] }>("/api/v1/membership/me"),
  membershipPlans: () => request<{ items: MembershipPlan[] }>("/api/v1/membership/plans"),
  podBlanks: (page: PageOptions = {}) => request<{ items: PodBlank[]; next_cursor: string | null }>(`/api/v1/pod/blanks?${pageQuery(page)}`),
  podBlank: (id: string) => request<{ blank: PodBlank }>(`/api/v1/pod/blanks/${id}`),
  createPodBlank: (payload: { category: string; material: string; name?: string; confirmed_attributes?: Record<string, unknown>; product_visual_style?: Record<string, unknown> }) =>
    request<{ blank: PodBlank }>("/api/v1/pod/blanks", { method: "POST", body: JSON.stringify(payload) }),
  updatePodBlank: (id: string, payload: Record<string, unknown>) => request<{ blank: PodBlank }>(`/api/v1/pod/blanks/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  addPodBlankReference: (id: string, payload: { asset_id: string; reference_role: "primary" | "detail" | "lifestyle"; sort_order?: number; is_supplier_reference?: boolean }) =>
    request<{ reference: PodBlankReference }>(`/api/v1/pod/blanks/${id}/references`, { method: "POST", body: JSON.stringify(payload) }),
  analyzePodBlank: (id: string) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/blanks/${id}/analysis`, { method: "POST", headers: { "Idempotency-Key": `pod-blank-analysis:${id}:${crypto.randomUUID()}` } }),
  podProjects: (page: PageOptions = {}) => request<{ items: PodProject[]; next_cursor: string | null }>(`/api/v1/pod/projects?${pageQuery(page)}`),
  createPodProject: (payload: { blank_id: string; name?: string }) => request<{ project: PodProject }>("/api/v1/pod/projects", { method: "POST", body: JSON.stringify(payload) }),
  podProject: (id: string) => request<PodProjectDetail>(`/api/v1/pod/projects/${id}`),
  generatePodIdeas: (id: string, count: 10 | 20 | 50) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/projects/${id}/ideas/generate`, { method: "POST", headers: { "Idempotency-Key": `pod-ideas:${id}:${crypto.randomUUID()}` }, body: JSON.stringify({ count }) }),
  updatePodIdea: (id: string, status: "adopted" | "archived") => request<{ idea: PodIdea }>(`/api/v1/pod/ideas/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  bulkUpdatePodIdeas: (idea_ids: string[], status: "adopted" | "archived") => request<{ updated: number; status: string }>("/api/v1/pod/ideas/bulk-status", { method: "POST", body: JSON.stringify({ idea_ids, status }) }),
  generatePodDesigns: (id: string, count = 4) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/ideas/${id}/design-concepts/generate`, { method: "POST", headers: { "Idempotency-Key": `pod-designs:${id}:${crypto.randomUUID()}` }, body: JSON.stringify({ count }) }),
  updatePodConcept: (id: string, status: "adopted" | "archived") => request<{ design_concept: PodDesignConcept }>(`/api/v1/pod/design-concepts/${id}`, { method: "PATCH", body: JSON.stringify({ status }) }),
  generatePodPrints: (id: string) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/design-concepts/${id}/print-candidates/generate`, { method: "POST", headers: { "Idempotency-Key": `pod-prints:${id}:${crypto.randomUUID()}` } }),
  approvePodPrintMaster: (id: string) => request<{ print_master: PodPrintMaster; product: PodProduct }>(`/api/v1/pod/print-candidates/${id}/approve-master`, { method: "POST" }),
  generatePodImageStrategy: (id: string) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/products/${id}/image-set/strategy/generate`, { method: "POST", headers: { "Idempotency-Key": `pod-image-strategy:${id}:${crypto.randomUUID()}` } }),
  updatePodImageSlot: (id: string, payload: Partial<Pick<PodImageSlot, "title" | "scene_prompt" | "composition_prompt" | "style_prompt" | "sort_order">>) => request<{ image_slot: PodImageSlot }>(`/api/v1/pod/image-slots/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  generatePodImageSlot: (productId: string, slotId: string, payload: { scene_prompt?: string; composition_prompt?: string; style_prompt?: string; size?: string; quality?: string } = {}) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/products/${productId}/image-slots/${slotId}/generate`, { method: "POST", headers: { "Idempotency-Key": `pod-image-slot:${slotId}:${crypto.randomUUID()}` }, body: JSON.stringify(payload) }),
  bulkGeneratePodImageSlots: (productId: string, slot_ids: string[], payload: { scene_prompt?: string; composition_prompt?: string; style_prompt?: string; size?: string; quality?: string } = {}) => request<{ submitted: number; jobs: { job_id: string; created: boolean; dispatched: boolean; status: string }[] }>(`/api/v1/pod/products/${productId}/image-slots/bulk-generate`, { method: "POST", headers: { "Idempotency-Key": `pod-image-slots:${productId}:${crypto.randomUUID()}` }, body: JSON.stringify({ slot_ids, ...payload }) }),
  generatePodProductCopy: (id: string) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/products/${id}/copy/generate`, { method: "POST", headers: { "Idempotency-Key": `pod-copy:${id}:${crypto.randomUUID()}` } }),
  updatePodProductCopy: (id: string, payload: Partial<Pick<PodProductCopy, "product_title" | "product_description" | "selling_points" | "search_keywords" | "content_warnings">>) => request<{ product_copy: PodProductCopy }>(`/api/v1/pod/product-copies/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  archivePodProductCopy: (id: string) => request<{ product_copy: PodProductCopy }>(`/api/v1/pod/product-copies/${id}`, { method: "DELETE" }),
  generatePodPrimaryVisual: (id: string, payload: { scene?: string; composition?: string; size?: string; quality?: string } = {}) => request<{ job: { job_id: string; created: boolean; dispatched: boolean; status: string } }>(`/api/v1/pod/products/${id}/primary-visual/generate`, { method: "POST", headers: { "Idempotency-Key": `pod-visual:${id}:${crypto.randomUUID()}` }, body: JSON.stringify(payload) }),
  createPodReview: (payload: { target_type: "blank" | "idea" | "print_candidate" | "image_slot" | "product"; target_id: string; gate: "G0" | "G1" | "G2" | "G3"; decision: "approved" | "rejected"; note?: string }) => request<{ review: { id: string } }>("/api/v1/pod/reviews", { method: "POST", body: JSON.stringify(payload) }),
};

/** Limit bandwidth pressure while keeping input order and each successful upload. */
export async function uploadAssets(files: File[], onSettled: (completed: number) => void) {
  const results: PromiseSettledResult<Asset>[] = new Array(files.length);
  let next = 0;
  let completed = 0;
  async function worker() {
    while (next < files.length) {
      const index = next++;
      try { results[index] = { status: "fulfilled", value: (await api.uploadAsset(files[index])).asset }; }
      catch (reason) { results[index] = { status: "rejected", reason }; }
      onSettled(++completed);
    }
  }
  await Promise.all(Array.from({ length: Math.min(2, files.length) }, () => worker()));
  return results;
}
