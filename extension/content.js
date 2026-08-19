chrome.runtime.onMessage.addListener(
  (message, sender, sendResponse) => {
    if (message.type === "GET_PAGE_DATA") {
      sendResponse({
        text: document.body?.innerText || ""
      });
    }

    return true;
  }
);
