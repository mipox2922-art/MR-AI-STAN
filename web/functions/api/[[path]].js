export async function onRequest(context) {
  const incoming = new URL(context.request.url);
  const pathname = incoming.pathname.replace(/^\/api(?=\/|$)/, "") || "/";

  // Preferred production path: forward through Pages to the separate Python API host.
  // The browser still talks only to https://mr-ai-stan.pages.dev/api/*.
  const apiOrigin = String(context.env.MR_AI_API_URL || "").trim();
  if (apiOrigin) {
    let base;
    try {
      base = new URL(apiOrigin);
    } catch {
      return Response.json(
        { detail: "MR_AI_API_URL must be a valid HTTPS API origin." },
        { status: 503 },
      );
    }

    if (base.protocol !== "https:") {
      return Response.json(
        { detail: "MR_AI_API_URL must use HTTPS." },
        { status: 503 },
      );
    }

    const target = new URL(base.origin);
    target.pathname = pathname;
    target.search = incoming.search;
    return fetch(new Request(target, context.request));
  }

  // Keep the existing service binding as a fallback during migration.
  if (context.env.MR_AI_API) {
    const target = new URL(context.request.url);
    target.pathname = pathname;
    return context.env.MR_AI_API.fetch(new Request(target, context.request));
  }

  return Response.json(
    {
      detail:
        "MR AI API is not connected. Set the Cloudflare Pages production variable MR_AI_API_URL to the deployed backend HTTPS origin.",
    },
    { status: 503 },
  );
}
