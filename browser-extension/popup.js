function setStatus(ok, port) {
  const dot = document.getElementById("dot");
  const txt = document.getElementById("txt");
  if (ok) {
    dot.style.background = "#3f8f4a";
    txt.textContent = "Verbunden (Port " + port + ")";
  } else {
    dot.style.background = "#b3261e";
    txt.textContent = "Tool nicht erreichbar (Port " + port + ")";
  }
}

chrome.runtime.sendMessage({ type: "ping" }, (resp) => {
  if (chrome.runtime.lastError || !resp) {
    setStatus(false, "?");
    return;
  }
  setStatus(resp.ok, resp.port);
});

document.getElementById("opt").addEventListener("click", () => {
  chrome.runtime.openOptionsPage();
});
