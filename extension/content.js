(() => {
  const SOURCE = "mr-ai-stan";

  function reply(requestId, ok, result, error = null) {
    window.postMessage({
      source: SOURCE,
      type: "MR_AI_BROWSER_RESULT",
      requestId,
      ok,
      result,
      error
    }, "*");
  }

  async function runAction(message) {
    const requestId = message.requestId;
    const action = message.action;
    try {
      if (action === "GET_PAGE_DATA") {
        return {
          title: document.title,
          url: location.href,
          text: (document.body?.innerText || "").slice(0, 30000)
        };
      }

      if (action === "CLICK") {
        const element = document.querySelector(message.selector);
        if (!element) throw new Error("Element not found");
        element.click();
        return { clicked: true, selector: message.selector };
      }

      if (action === "TYPE") {
        const element = document.querySelector(message.selector);
        if (!element) throw new Error("Element not found");
        const value = String(message.value ?? "");
        element.focus();
        if ("value" in element) {
          const setter = Object.getOwnPropertyDescriptor(
            element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
            "value"
          )?.set;
          setter?.call(element, value);
          if (!setter) element.value = value;
          element.dispatchEvent(new Event("input", { bubbles: true }));
          element.dispatchEvent(new Event("change", { bubbles: true }));
        } else {
          element.textContent = value;
          element.dispatchEvent(new InputEvent("input", { bubbles: true, data: value, inputType: "insertText" }));
        }
        return { typed: true, selector: message.selector };
      }

      if (action === "SCROLL") {
        const amount = Number(message.amount ?? 600);
        window.scrollBy({ top: amount, behavior: "smooth" });
        return { scrolled: amount };
      }

      if (action === "DRAG") {
        const element = document.querySelector(message.selector);
        if (!element) throw new Error("Element not found");
        const rect = element.getBoundingClientRect();
        const startX = rect.left + rect.width / 2;
        const startY = rect.top + rect.height / 2;
        const endX = startX + Number(message.dx ?? 0);
        const endY = startY + Number(message.dy ?? 0);

        element.dispatchEvent(new PointerEvent("pointerdown", {
          bubbles: true, clientX: startX, clientY: startY, buttons: 1
        }));
        element.dispatchEvent(new PointerEvent("pointermove", {
          bubbles: true, clientX: endX, clientY: endY, buttons: 1
        }));
        element.dispatchEvent(new PointerEvent("pointerup", {
          bubbles: true, clientX: endX, clientY: endY, buttons: 0
        }));

        return { dragged: true, selector: message.selector, dx: Number(message.dx ?? 0), dy: Number(message.dy ?? 0) };
      }

      if (action === "NAVIGATE") {
        const url = new URL(String(message.url), location.href);
        if (!["http:", "https:"].includes(url.protocol)) {
          throw new Error("Only HTTP(S) navigation is allowed");
        }
        location.href = url.href;
        return { navigating: true, url: url.href };
      }

      throw new Error("Unsupported browser action: " + action);
    } catch (error) {
      throw error;
    }
  }

  window.addEventListener("message", async (event) => {
    if (event.source !== window || !event.data || event.data.source !== SOURCE) return;
    if (event.data.type !== "MR_AI_BROWSER_ACTION") return;

    const result = await runAction(event.data);
    reply(event.data.requestId, true, result);
  });
})();
