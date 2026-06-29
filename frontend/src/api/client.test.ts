import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiRequest,
  deleteSession,
  getSession,
  getSessions,
  undoSession,
} from "./client";

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("builds sessions query strings with defined filters only", async () => {
    mockJsonResponse({ sessions: [], total: 0 });

    await getSessions({
      q: "hello world",
      dir: "C:/repo/app",
      model: "",
      limit: 20,
      offset: 5,
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/sessions?q=hello+world&dir=C%3A%2Frepo%2Fapp&limit=20&offset=5",
      expect.objectContaining({
        headers: expect.objectContaining({ Accept: "application/json" }),
      }),
    );
  });

  it("encodes path parameters for session endpoints", async () => {
    mockJsonResponse({ session: {}, messages: [], message_count: 0 });
    await getSession("ses/with space");

    expect(fetch).toHaveBeenLastCalledWith(
      "/api/sessions/ses%2Fwith%20space",
      expect.any(Object),
    );

    mockJsonResponse({ status: "ok" });
    await deleteSession("ses/with space");
    await undoSession("ses/with space");

    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/sessions/ses%2Fwith%20space",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/api/sessions/ses%2Fwith%20space/undo",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("sets JSON headers when a request body is present", async () => {
    mockJsonResponse({ ok: true });

    await apiRequest<{ ok: boolean }>("/api/example", {
      method: "POST",
      body: JSON.stringify({ value: 1 }),
      headers: { "X-Test": "yes" },
    });

    expect(fetch).toHaveBeenCalledWith(
      "/api/example",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ value: 1 }),
        headers: expect.objectContaining({
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-Test": "yes",
        }),
      }),
    );
  });

  it("throws ApiError with status and parsed payload on failed responses", async () => {
    mockJsonResponse({ error: "会话不存在" }, { status: 404, statusText: "Not Found" });

    await expect(apiRequest("/api/missing")).rejects.toMatchObject({
      name: "ApiError",
      message: "会话不存在",
      status: 404,
      payload: { error: "会话不存在" },
    } satisfies Partial<ApiError>);
  });
});

function mockJsonResponse(payload: unknown, init: ResponseInit = {}) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(payload), {
      status: init.status ?? 200,
      statusText: init.statusText,
      headers: { "Content-Type": "application/json" },
    }),
  );
}
