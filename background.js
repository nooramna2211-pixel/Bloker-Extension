const NATIVE_HOST_NAME = "com.bloker.content_filter";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "get-protection-state") {
    return false;
  }

  let port;
  try {
    port = chrome.runtime.connectNative(NATIVE_HOST_NAME);
  } catch (error) {
    console.error("Bloker native host connection failed:", error);
    sendResponse({ enabled: true, bridgeAvailable: false });
    return false;
  }

  let replied = false;
  const respond = (response) => {
    if (!replied) {
      replied = true;
      sendResponse(response);
    }
  };

  port.onMessage.addListener((response) => {
    respond({
      enabled: response && response.enabled === false ? false : true,
      bridgeAvailable: true
    });
    port.disconnect();
  });
  port.onDisconnect.addListener(() => {
    if (chrome.runtime.lastError) {
      console.error("Bloker native host error:", chrome.runtime.lastError.message);
    }
    respond({ enabled: true, bridgeAvailable: false });
  });
  port.postMessage({ type: "get-state" });
  return true;
});
