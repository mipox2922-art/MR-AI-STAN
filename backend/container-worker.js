import { Container, getContainer } from "@cloudflare/containers";

const INSTANCE_NAME = "mr-ai-stan-api";
const REQUIRED_SECRETS = [
  "SECRET_KEY",
  "DATABASE_URL",
  "DATABASE_SSL_CA_CERT",
  "CLOUDFLARE_CRON_SECRET",
];

function missingRuntimeSecrets(workerEnv) {
  return REQUIRED_SECRETS.filter((name) => {
    const value = workerEnv[name];
    return typeof value !== "string" || value.trim().length === 0;
  });
}

export class MrAiApiContainer extends Container {
  defaultPort = 8000;
  pingEndpoint = "health";
  // Cron runs every minute; keep FastAPI warm and avoid reconnecting to Supabase
  // on each tick. The Cloudflare Containers runtime is usage-billed.
  sleepAfter = "5m";

  constructor(ctx, workerEnv) {
    super(ctx, workerEnv);
    this.envVars = {
      PORT: "8000",
      SERVERLESS_MODE: "false",
      SCHEDULER_ENABLED: "false",
      SECRET_KEY: String(workerEnv.SECRET_KEY || ""),
      DATABASE_URL: String(workerEnv.DATABASE_URL || ""),
      DATABASE_SSL_CA_CERT: String(workerEnv.DATABASE_SSL_CA_CERT || ""),
      CORS_ORIGINS: String(
        workerEnv.CORS_ORIGINS || "https://mr-ai-stan.pages.dev",
      ),
      GEMINI_API_KEY: String(workerEnv.GEMINI_API_KEY || ""),
      GEMINI_MODEL: String(workerEnv.GEMINI_MODEL || "gemini-2.5-flash"),
      GEMINI_TIER: String(workerEnv.GEMINI_TIER || "FREE"),
      KIMI_API_KEY: String(workerEnv.KIMI_API_KEY || ""),
      KIMI_MODEL: String(workerEnv.KIMI_MODEL || "kimi-k2"),
      KIMI_BASE_URL: String(
        workerEnv.KIMI_BASE_URL || "https://api.moonshot.ai/v1",
      ),
      SEARXNG_URL: String(workerEnv.SEARXNG_URL || ""),
      GMAIL_CLIENT_ID: String(workerEnv.GMAIL_CLIENT_ID || ""),
      GMAIL_CLIENT_SECRET: String(workerEnv.GMAIL_CLIENT_SECRET || ""),
      GMAIL_REDIRECT_URI: String(workerEnv.GMAIL_REDIRECT_URI || ""),
      GMAIL_SCOPES: String(
        workerEnv.GMAIL_SCOPES || "https://www.googleapis.com/auth/gmail.readonly",
      ),
      CLOUDFLARE_CRON_SECRET: String(workerEnv.CLOUDFLARE_CRON_SECRET || ""),
    };
  }
}

export default {
  async fetch(request, workerEnv) {
    const missing = missingRuntimeSecrets(workerEnv);
    if (missing.length) {
      return Response.json(
        {
          detail:
            "MR AI API is not configured yet. Add the required secrets to the Cloudflare Worker.",
          missing,
        },
        { status: 503 },
      );
    }

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
    const missing = missingRuntimeSecrets(workerEnv);
    if (missing.length) {
      console.warn(
        "Cloudflare scheduler skipped; configure the required API Worker secrets:",
        missing.join(", "),
      );
      return;
    }

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
