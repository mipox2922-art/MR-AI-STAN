(() => {
  const MAX_PAGE_TEXT = 20000;

  function pageData() {
    return {
      title: document.title || "",
      url: window.location.href,
      text: document.body?.innerText?.slice(0, MAX_PAGE_TEXT) || ""
    };
  }

  function resolveTarget(selector) {
    if (!selector || typeof selector !== "string") {
      throw new Error("A CSS selector is required.");
    }
    const element = document.querySelector(selector);
    if (!element) throw new Error(`Element not found: ${selector}`);
    return element;
  }

  function describeElement(element) {
    return {
      tag: element.tagName?.toLowerCase() || "",
      id: element.id || "",
      classes: typeof element.className === "string" ? element.className : "",
      text: (element.innerText || element.textContent || "").trim().slice(0, 240),
      ariaLabel: element.getAttribute?.("aria-label") || ""
    };
  }

  function setNativeValue(element, value) {
    const prototype =
      element instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
    descriptor?.set ? descriptor.set.call(element, value) : (element.value = value);
  }

  async function allowedHost(hostname) {
    const stored = await chrome.storage.local.get("mr_ai_browser_allowlist");
    const entries = Array.isArray(stored.mr_ai_browser_allowlist)
      ? stored.mr_ai_browser_allowlist.filter(value => typeof value === "string").map(value => value.trim().toLowerCase())
      : [];
    const host = String(hostname || "").toLowerCase();
    return Boolean(host && entries.some(entry => host === entry || host.endsWith("." + entry)));
  }

  function highRiskClick(element) {
    const description = describeElement(element);
    const form = element.closest?.("form");
    const text = [
      description.text,
      description.ariaLabel,
      element.getAttribute?.("title") || "",
      element.getAttribute?.("name") || "",
      element.getAttribute?.("value") || "",
      element.getAttribute?.("data-testid") || "",
      element.getAttribute?.("href") || ""
    ].join(" ").toLowerCase();
    const submitControl = Boolean(form) && (
      (element.tagName === "BUTTON" && String(element.type || "submit").toLowerCase() === "submit") ||
      (element.tagName === "INPUT" && ["submit", "image"].includes(String(element.type || "").toLowerCase()))
    );
    const words = /\b(pay|payment|purchase|buy now|checkout|submit|send|apply|application|download|upload|delete|remove|transfer|order|withdraw|confirm booking|post message|publish|send reply|reply now)\b/i;
    if (submitControl) return { required: true, risk: "FORM_SUBMISSION", reason: "Kutuma fomu au kuwasilisha mabadiliko kunahitaji idhini ya Boss." };
    if (words.test(text)) return { required: true, risk: "EXTERNAL_SIDE_EFFECT", reason: "Malipo, kutuma, kuomba kazi, kupakua, kufuta au kuchapisha kunahitaji idhini ya Boss." };
    const href = String(element.getAttribute?.("href") || "").toLowerCase();
    if (/\.(pdf|zip|exe|msi|dmg|apk|7z|rar)(?:[?#]|$)/i.test(href)) {
      return { required: true, risk: "DOWNLOAD", reason: "Kiungo hiki kinaweza kuanzisha upakuaji; idhini ya Boss inahitajika." };
    }
    return { required: false, risk: "LOW", reason: null };
  }

  function sensitiveInput(element) {
    const type = String(element.type || "").toLowerCase();
    const autocomplete = String(element.getAttribute?.("autocomplete") || "").toLowerCase();
    const hint = [
      element.name, element.id, element.getAttribute?.("aria-label"),
      element.getAttribute?.("placeholder"), autocomplete
    ].filter(Boolean).join(" ").toLowerCase();
    return type === "password" ||
      ["one-time-code", "cc-number", "cc-csc", "cc-exp"].includes(autocomplete) ||
      /\b(password|passcode|otp|one.?time.?code|credit.?card|card.?number|cvv|cvc|security.?code|bank.?pin)\b/i.test(hint);
  }

  async function performAction(action, payload = {}) {
    const currentHost = window.location.hostname.toLowerCase();
    if (!(await allowedHost(currentHost))) {
      throw new Error("BLOCKED_BY_ALLOWLIST: Domain hii haijaidhinishwa na Boss Ferisi.");
    }
    switch (action) {
      case "GET_PAGE_DATA":
        return { verified: true, action, page: pageData() };

      case "CLICK": {
        const element = resolveTarget(payload.selector);
        if (element.disabled) throw new Error("Target element is disabled.");
        const risk = highRiskClick(element);
        if (risk.required && payload.boss_approved !== true) {
          return { verified: false, approvalRequired: true, action, risk: risk.risk,
            reason: risk.reason, host: window.location.hostname, element: describeElement(element) };
        }
        const beforeUrl = window.location.href;
        const description = describeElement(element);
        element.scrollIntoView({ block: "center", inline: "center", behavior: "auto" });
        element.click();
        return { verified: false, dispatched: true, action, risk: risk.risk, element: description,
          beforeUrl, afterUrl: window.location.href,
          note: "DOM click event dispatched; resulting external action requires independent confirmation." };
      }

      case "TYPE": {
        const element = resolveTarget(payload.selector);
        const value = String(payload.value ?? "");
        if (sensitiveInput(element)) {
          throw new Error("BLOCKED_SENSITIVE_FIELD: MR AI haiingizi nywila, OTP, PIN au taarifa za kadi kupitia Browser Hands.");
        }

        if (element.isContentEditable) {
          element.focus();
          document.execCommand?.("selectAll", false);
          element.textContent = value;
          element.dispatchEvent(new InputEvent("input", {
            bubbles: true,
            inputType: "insertText",
            data: value
          }));
          element.dispatchEvent(new Event("change", { bubbles: true }));
          return {
            verified: element.textContent === value,
            action,
            element: describeElement(element),
            valueLength: value.length
          };
        }

        if (!("value" in element)) {
          throw new Error("Target element does not expose a writable value.");
        }

        element.focus();
        setNativeValue(element, value);
        element.dispatchEvent(new InputEvent("input", {
          bubbles: true,
          inputType: "insertText",
          data: value
        }));
        element.dispatchEvent(new Event("change", { bubbles: true }));

        return {
          verified: element.value === value,
          action,
          element: describeElement(element),
          valueLength: value.length
        };
      }

      case "SCROLL": {
        const amount = Number(payload.amount ?? 600);
        if (!Number.isFinite(amount)) throw new Error("Scroll amount must be numeric.");

        const beforeY = window.scrollY;
        window.scrollBy({ top: amount, left: 0, behavior: "auto" });
        await new Promise(resolve => requestAnimationFrame(() => resolve()));

        return {
          verified: window.scrollY !== beforeY || Math.abs(amount) < 2,
          action,
          beforeY,
          afterY: window.scrollY,
          maxY: Math.max(0, document.documentElement.scrollHeight - window.innerHeight)
        };
      }

      case "NAVIGATE": {
        const rawUrl = String(payload.url || "").trim();
        let url;
        try {
          url = new URL(rawUrl, window.location.href);
        } catch {
          throw new Error("Invalid navigation URL.");
        }

        if (!["http:", "https:"].includes(url.protocol)) {
          throw new Error("Only HTTP(S) navigation is allowed.");
        }

        const target = url.toString();
        if (!(await allowedHost(url.hostname))) throw new Error("BLOCKED_BY_ALLOWLIST: Destination domain haijaidhinishwa na Boss Ferisi.");
        const mayDownload = /.(pdf|zip|exe|msi|dmg|apk|7z|rar)(?:[?#]|$)/i.test(url.pathname + url.search);
        if (mayDownload && payload.boss_approved !== true) {
          return { verified: false, approvalRequired: true, action, risk: "DOWNLOAD", host: url.hostname,
            target, reason: "Destination inaweza kupakua faili; idhini ya Boss inahitajika." };
        }
        setTimeout(() => window.location.assign(target), 50);
        return { verified: false, dispatched: true, action, target, risk: mayDownload ? "DOWNLOAD" : "LOW",
          note: "Navigation was requested; the destination and its resulting state have not yet been verified." };
      }

      case "DRAG": {
        const element = resolveTarget(payload.selector);
        const dx = Number(payload.dx ?? 0);
        const dy = Number(payload.dy ?? 0);
        if (!Number.isFinite(dx) || !Number.isFinite(dy)) {
          throw new Error("Drag offsets must be numeric.");
        }

        element.scrollIntoView({ block: "center", inline: "center", behavior: "auto" });
        const rect = element.getBoundingClientRect();
        const startX = rect.left + rect.width / 2;
        const startY = rect.top + rect.height / 2;
        const endX = startX + dx;
        const endY = startY + dy;

        element.dispatchEvent(new Event("dragstart", { bubbles: true, cancelable: true }));

        for (const [type, x, y] of [
          ["pointerdown", startX, startY],
          ["mousedown", startX, startY],
          ["pointermove", endX, endY],
          ["mousemove", endX, endY],
          ["pointerup", endX, endY],
          ["mouseup", endX, endY]
        ]) {
          const EventCtor = type.startsWith("pointer") && typeof PointerEvent !== "undefined"
            ? PointerEvent
            : MouseEvent;
          element.dispatchEvent(new EventCtor(type, {
            bubbles: true,
            cancelable: true,
            clientX: x,
            clientY: y,
            buttons: type.includes("up") ? 0 : 1,
            pointerId: 1
          }));
        }

        element.dispatchEvent(new Event("dragend", { bubbles: true, cancelable: true }));

        return {
          verified: false,
          dispatched: true,
          action,
          element: describeElement(element),
          start: { x: Math.round(startX), y: Math.round(startY) },
          end: { x: Math.round(endX), y: Math.round(endY) },
          note: "Synthetic pointer/mouse events were dispatched, but the resulting application state was not independently verified; complex site-specific DnD may require Playwright."
        };
      }

      default:
        throw new Error(`Unsupported browser action: ${action}`);
    }
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type === "GET_PAGE_DATA") {
      sendResponse(pageData());
      return true;
    }

    if (message?.type !== "MR_AI_BROWSER_ACTION") return false;

    performAction(message.action, message)
      .then(result => sendResponse({ ok: true, result }))
      .catch(error => sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : String(error)
      }));

    return true;
  });

  // Expose the extension ID to the MR AI web app through shared DOM state.
  // The web app only uses this value to initiate externally_connectable messaging.
  const root = document.documentElement;
  if (root && !root.dataset.mrAiExtensionId) {
    root.dataset.mrAiExtensionId = chrome.runtime.id;
  }
})();
