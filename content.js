const terms = [
  "porn", "porno", "pornography", "sex", "sexy", "xxx", "nude", "nudity",
  "adult video", "adult content", "nsfw", "uncut video", "hot video",
  "gandi video", "kharab video", "blue film", "pornhub", "xvideos", "xnxx",
  "redtube", "tube8", "xhamster", "youporne", "brazzers", "onlyfans",
  "camgirl", "cam girl", "cam boy", "hamsterx", "porn.com", "pornhub.com",
  "xvideos.com", "xnxx.com", "redtube.com", "tube8.com"
];
let protectionEnabled = true;

function normalize(value) {
  return value.normalize("NFKC").toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

function containsBlockedTerm(value) {
  const text = normalize(value);
  return terms.some((term) => {
    const normalizedTerm = normalize(term);
    return normalizedTerm.length > 0 && text.includes(normalizedTerm);
  });
}

function isSearchField(element) {
  if (!(element instanceof HTMLElement)) return false;
  if (element.isContentEditable || element.getAttribute("role") === "searchbox") {
    return true;
  }
  if (!(element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement)) {
    return false;
  }
  if (element instanceof HTMLInputElement && ["password", "hidden"].includes(element.type)) {
    return false;
  }
  const metadata = [
    element.type,
    element.name,
    element.id,
    element.placeholder,
    element.getAttribute("aria-label")
  ].join(" ").toLocaleLowerCase();
  return /search|query|keyword/.test(metadata);
}

function fieldValue(element) {
  return "value" in element ? element.value : element.textContent || "";
}

function showNotice() {
  const root = document.documentElement;
  if (!root) return;

  let style = document.getElementById("bloker-block-style");
  if (!style) {
    style = document.createElement("style");
    style.id = "bloker-block-style";
    (document.head || root).appendChild(style);
  }
  style.textContent = `
    html, body {
      background: #fff !important;
    }
    body {
      visibility: hidden !important;
    }
    #search, #main, #cnt, #rcnt, div[role="main"], c-wiz,
    #rso, #center_col, #top_nav, #appbar, #tads, #tadsb {
      display: none !important;
      visibility: hidden !important;
      opacity: 0 !important;
      pointer-events: none !important;
    }
    #bloker-full-overlay {
      position: fixed !important;
      top: 0 !important;
      left: 0 !important;
      right: 0 !important;
      bottom: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      min-width: 100vw !important;
      min-height: 100vh !important;
      margin: 0 !important;
      padding: 0 !important;
      box-sizing: border-box !important;
      z-index: 2147483647 !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      visibility: visible !important;
      opacity: 1 !important;
      pointer-events: auto !important;
      background: #fff !important;
      font: 16px Arial, sans-serif !important;
    }
  `;

  let overlay = document.getElementById("bloker-full-overlay");
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.id = "bloker-full-overlay";
    const message = document.createElement("div");
    message.style.cssText =
      "max-width:560px;margin:24px;padding:32px;text-align:center;" +
      "color:#721c24;background:#f8d7da;border:2px solid #f5c6cb;" +
      "border-radius:8px;box-shadow:0 0 20px #0003";
    const heading = document.createElement("h1");
    heading.textContent = "Access Blocked";
    const description = document.createElement("p");
    description.textContent = "This search was blocked by Bloker Protection.";
    message.append(heading, description);
    overlay.appendChild(message);
  }

  // Keep the overlay outside the hidden body so Google's page styles cannot cover it.
  if (overlay.parentElement !== root) root.appendChild(overlay);
  Object.assign(overlay.style, {
    position: "fixed",
    top: "0",
    left: "0",
    width: "100vw",
    height: "100vh",
    zIndex: "2147483647",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    visibility: "visible",
    opacity: "1",
    pointerEvents: "auto",
    backgroundColor: "white",
    margin: "0",
    padding: "0",
    boxSizing: "border-box"
  });
}

function removeNotice() {
  document.getElementById("bloker-full-overlay")?.remove();
  document.getElementById("bloker-block-style")?.remove();
}

function checkCurrentPage() {
  if (!protectionEnabled || terms.length === 0) return;

  const currentUrl = new URL(window.location.href);
  const urlSearchText = [currentUrl.href, ...currentUrl.searchParams.values()].join(" ");
  const pageText = document.body?.innerText || "";
  const searchText = Array.from(
    document.querySelectorAll("input, textarea, [contenteditable='true'], [role='searchbox']")
  )
    .filter(isSearchField)
    .map(fieldValue)
    .join(" ");

  if (
    containsBlockedTerm(urlSearchText) ||
    containsBlockedTerm(pageText) ||
    containsBlockedTerm(searchText)
  ) {
    showNotice();
  }
}

function preventBlockedSearch(event) {
  if (!protectionEnabled || !isSearchField(event.target)) return;
  if (!containsBlockedTerm(fieldValue(event.target))) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  showNotice();
}

document.addEventListener("input", preventBlockedSearch, true);
document.addEventListener("submit", (event) => {
  if (!protectionEnabled || !(event.target instanceof HTMLFormElement)) return;
  const hasBlockedSearch = Array.from(event.target.elements).some(
    (field) => isSearchField(field) && containsBlockedTerm(fieldValue(field))
  );
  if (hasBlockedSearch) {
    event.preventDefault();
    event.stopImmediatePropagation();
    showNotice();
  }
}, true);

checkCurrentPage();
window.setInterval(checkCurrentPage, 300);
chrome.runtime.sendMessage({ type: "get-protection-state" }, (state) => {
  if (chrome.runtime.lastError) {
    console.error(
      "Bloker could not read protection state:",
      chrome.runtime.lastError.message
    );
    protectionEnabled = true;
  } else {
    protectionEnabled = !state || state.enabled !== false;
  }
  if (protectionEnabled) {
    checkCurrentPage();
  } else {
    removeNotice();
  }
});
