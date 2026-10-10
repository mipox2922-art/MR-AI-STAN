export async function onRequest(context) {
  const incoming = new URL(context.request.url);
  const pathname = incoming.pathname.replace(/^\/api(?=\/|$)/, "") || "/";

  // Keep API traffic inside Cloudflare through a Worker service binding.
  // The browser uses the same-origin /api path; no Render/API origin is needed.
  const api = context.env.MR_AI_API;
  if (!api) {
    return Response.json(
      {
        detail:
          "MR AI API is not connected. Configure the Cloudflare Pages service binding MR_AI_API to the mr-ai-stan-api Worker.",
      },
      { status: 503 },
    );
  }

  const target = new URL(context.request.url);
  target.pathname = pathname;
  return api.fetch(new Request(target, context.request));
}
