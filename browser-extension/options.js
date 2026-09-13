const DEFAULTS = { enabled: true, port: 47800,
  patterns: "civitai.com, civitai.red, civitai.green" };

function load() {
  chrome.storage.sync.get(DEFAULTS, (c) => {
    document.getElementById("enabled").checked = c.enabled !== false;
    document.getElementById("port").value = parseInt(c.port, 10) || DEFAULTS.port;
    document.getElementById("patterns").value =
      typeof c.patterns === "string" ? c.patterns : DEFAULTS.patterns;
  });
}

function save() {
  const cfg = {
    enabled: document.getElementById("enabled").checked,
    port: parseInt(document.getElementById("port").value, 10) || DEFAULTS.port,
    patterns: document.getElementById("patterns").value.trim()
      || DEFAULTS.patterns
  };
  chrome.storage.sync.set(cfg, () => {
    const s = document.getElementById("status");
    s.textContent = "Gespeichert.";
    s.style.color = "#3f8f4a";
    setTimeout(() => (s.textContent = ""), 2000);
  });
}

document.getElementById("save").addEventListener("click", save);
load();
