chrome.runtime.onInstalled.addListener(() => {
  console.log("MR AI Browser Hands installed.");
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "MR_AI_GET_ACTIVE_TAB") return;

  chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
    const tab = tabs[0];
    sendResponse(tab ? {
      id: tab.id,
      title: tab.title || "",
      url: tab.url || ""
    } : null);
  });

  return true;
});
