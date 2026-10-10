export async function onRequest(context) {
  const incoming = new URL(context.request.url);
  const pathname = incoming.pathname.replace(/^\/api(?=\/|$)/, "") || "/";
  const apiOrigin = String(context.env.MR_AI_API_URL || "").trim();

  if (!apiOrigin) {
    return Response.json(
      {
        detail:
          "MR AI API is not configured. Set the Cloudflare Pages production variable MR_AI_API_URL to the HTTPS origin of the Render FastAPI service.",
      },
      { status: 503 },
    );
  }

  let base;
  try {
    base = new URL(apiOrigin);
  } catch {
    return Response.json(
      { detail: "MR_AI_API_URL must be a valid HTTPS API origin." },
      { status: 503 },
    );
  }

  if (
    base.protocol !== "https:" ||
    base.username ||
    base.password ||
    base.pathname !== "/" ||
    base.search ||
    base.hash
  ) {
    return Response.json(
      { detail: "MR_AI_API_URL must be an HTTPS origin without credentials, path, query, or fragment." },
      { status: 503 },
    );
  }

  const target = new URL(base.origin);
  target.pathname = pathname;
  target.search = incoming.search;

  // Keep browser requests same-origin and preserve authorization/body/method.
  return fetch(new Request(target, context.request));
}
