export async function onRequest(context) {
  const target = new URL(context.request.url);
  target.pathname = target.pathname.replace(/^\/api(?=\/|$)/, "") || "/";

  const request = new Request(target, context.request);
  return context.env.MR_AI_API.fetch(request);
}
