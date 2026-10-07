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

  async function performAction(action, payload = {}) {
    switch (action) {
      case "GET_PAGE_DATA":
        return { verified: true, action, page: pageData() };

      case "CLICK": {
        const element = resolveTarget(payload.selector);
        if (element.disabled) throw new Error("Target element is disabled.");
        const beforeUrl = window.location.href;
        const description = describeElement(element);
        element.scrollIntoView({ block: "center", inline: "center", behavior: "auto" });
        element.click();
        return {
          verified: true,
          action,
          element: description,
          beforeUrl,
          afterUrl: window.location.href,
          note: "DOM click dispatched. Navigation or app-side effects may continue asynchronously."
        };
      }

      case "TYPE": {
        const element = resolveTarget(payload.selector);
        const value = String(payload.value ?? "");

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
        setTimeout(() => window.location.assign(target), 50);
        return { verified: true, action, target, note: "Navigation started." };
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
          verified: true,
          action,
          element: describeElement(element),
          start: { x: Math.round(startX), y: Math.round(startY) },
          end: { x: Math.round(endX), y: Math.round(endY) },
          note: "Synthetic pointer/mouse drag events dispatched; complex site-specific DnD may require Playwright."
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
