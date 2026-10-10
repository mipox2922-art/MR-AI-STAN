import { Container, getContainer } from "@cloudflare/containers";
import { env } from "cloudflare:workers";

const INSTANCE_NAME = "mr-ai-stan-api";

export class MrAiApiContainer extends Container {
  defaultPort = 8000;
  sleepAfter = "30s";

  envVars = {
    PORT: "8000",
    SERVERLESS_MODE: "false",
    SCHEDULER_ENABLED: "false",
    SECRET_KEY: String(env.SECRET_KEY || ""),
    DATABASE_URL: String(env.DATABASE_URL || ""),
    DATABASE_SSL_CA_CERT: String(env.DATABASE_SSL_CA_CERT || ""),
    CORS_ORIGINS: String(env.CORS_ORIGINS || "https://mr-ai-stan.pages.dev"),
    GEMINI_API_KEY: String(env.GEMINI_API_KEY || ""),
    GEMINI_MODEL: String(env.GEMINI_MODEL || "gemini-2.5-flash"),
    GEMINI_TIER: String(env.GEMINI_TIER || "FREE"),
    KIMI_API_KEY: String(env.KIMI_API_KEY || ""),
    KIMI_MODEL: String(env.KIMI_MODEL || "kimi-k2"),
    KIMI_BASE_URL: String(env.KIMI_BASE_URL || "https://api.moonshot.ai/v1"),
    SEARXNG_URL: String(env.SEARXNG_URL || ""),
    GMAIL_CLIENT_ID: String(env.GMAIL_CLIENT_ID || ""),
    GMAIL_CLIENT_SECRET: String(env.GMAIL_CLIENT_SECRET || ""),
    GMAIL_REDIRECT_URI: String(env.GMAIL_REDIRECT_URI || ""),
    GMAIL_SCOPES: String(
      env.GMAIL_SCOPES || "https://www.googleapis.com/auth/gmail.readonly",
    ),
    CLOUDFLARE_CRON_SECRET: String(env.CLOUDFLARE_CRON_SECRET || ""),
  };
}

export default {
  async fetch(request, workerEnv) {
    if (!workerEnv.MR_AI_API_CONTAINER) {
      return Response.json(
        { detail: "Cloudflare API container binding is missing." },
        { status: 503 },
      );
    }

    const container = getContainer(
      workerEnv.MR_AI_API_CONTAINER,
      INSTANCE_NAME,
    );
    return container.fetch(request);
  },

  async scheduled(_controller, workerEnv) {
    const secret = String(workerEnv.CLOUDFLARE_CRON_SECRET || "");
    if (secret.length < 32) {
      console.error("Cloudflare scheduler is not configured with a strong secret.");
      return;
    }

    const container = getContainer(
      workerEnv.MR_AI_API_CONTAINER,
      INSTANCE_NAME,
    );
    const response = await container.fetch(
      new Request("http://mr-ai-internal/internal/cloudflare/scheduler-cycle", {
        method: "POST",
        headers: { "X-MR-AI-Cron-Secret": secret },
      }),
    );

    if (!response.ok) {
      const detail = await response.text();
      console.error(
        "Cloudflare scheduler cycle failed:",
        response.status,
        detail.slice(0, 500),
      );
      throw new Error(`Cloudflare scheduler cycle returned HTTP ${response.status}`);
    }
  },
};
