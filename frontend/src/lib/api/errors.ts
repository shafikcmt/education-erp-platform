/** RFC 9457 Problem Details returned by the API (docs/API_STANDARDS.md §4). */
export interface ProblemBody {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string;
  request_id?: string;
  retry_after?: number;
  errors?: { field: string; code: string; message: string }[];
}

/** Error thrown by `unwrap` for any non-2xx response. Never contains request bodies. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfter?: number;
  readonly fieldErrors: Record<string, string[]>;

  constructor(status: number, body: ProblemBody | undefined) {
    super(body?.detail ?? `HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = body?.code ?? (status === 0 ? "network_error" : "error");
    this.retryAfter = body?.retry_after;
    this.fieldErrors = {};
    for (const item of body?.errors ?? []) {
      (this.fieldErrors[item.field] ??= []).push(item.message);
    }
  }
}

export function isApiError(value: unknown, code?: string): value is ApiError {
  return value instanceof ApiError && (code === undefined || value.code === code);
}

/** Resolve an openapi-fetch result to its data, or throw `ApiError`. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await promise;
  } catch {
    throw new ApiError(0, undefined);
  }
  if (!result.response.ok) {
    throw new ApiError(result.response.status, result.error as ProblemBody | undefined);
  }
  return result.data as T;
}
