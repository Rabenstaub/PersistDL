// PersistDL Catcher – Service Worker (MV3)
// Faengt neu startende Downloads ab und schickt die URL an das lokale
// PersistDL-Tool. Der Browser-Download wird NUR abgebrochen, wenn das
// Tool die URL bestaetigt hat – laeuft das Tool nicht, laedt der Browser
// ganz normal selbst weiter (kein Datenverlust).

const DEFAULTS = {
  enabled: true,
  port: 47800,
  // Kommagetrennte Muster; ein Download wird abgefangen, wenn Host oder
  // URL eines dieser Muster enthaelt. Standard: Civitai inkl. Mirrors
  // (civitai.red / civitai.green).
  patterns: "civitai.com, civitai.red, civitai.green"
};

async function getCfg() {
  const c = await chrome.storage.sync.get(DEFAULTS);
  return {
    enabled: c.enabled !== false,
    port: parseInt(c.port, 10) || DEFAULTS.port,
    patterns: (typeof c.patterns === "string" ? c.patterns : DEFAULTS.patterns)
  };
}

function patternList(patterns) {
  return String(patterns)
    .split(/[\s,;\n]+/)
    .map(p => p.trim().toLowerCase())
    .filter(Boolean);
}

function matches(url, patterns) {
  let u;
  try {
    u = new URL(url);
  } catch (e) {
    return false;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  // Eigene / lokale Adressen niemals abfangen (Endlosschleife vermeiden)
  const host = u.hostname.toLowerCase();
  if (host === "127.0.0.1" || host === "localhost") return false;
  const low = url.toLowerCase();
  return patternList(patterns).some(p => host.includes(p) || low.includes(p));
}

async function notify(title, message) {
  try {
    await chrome.notifications.create({
      type: "basic",
      iconUrl: "icon128.png",
      title: "PersistDL – " + title,
      message: String(message || "").slice(0, 250)
    });
  } catch (e) {
    // Benachrichtigungen sind optional; Fehler ignorieren.
  }
}

chrome.downloads.onCreated.addListener(async (item) => {
  const cfg = await getCfg();
  if (!cfg.enabled) return;

  // WICHTIG: Civitai leitet auf CDN-Adressen um (Cloudflare-Speicher),
  // die "civitai.com" NICHT enthalten. Deshalb Start-URL, End-URL UND
  // Referrer (die Seite, von der geklickt wurde) pruefen.
  const url = item.url || "";
  const finalUrl = item.finalUrl || "";
  const referrer = item.referrer || "";
  const hit = [url, finalUrl, referrer].some(u => u && matches(u, cfg.patterns));
  if (!hit) return;

  // SOFORT pausieren, damit Chrome nicht weiterlaedt, waehrend wir das
  // Tool fragen. Bei Nichterreichbarkeit wird wieder fortgesetzt.
  let paused = false;
  try { await chrome.downloads.pause(item.id); paused = true; } catch (e) {}

  // Dem Tool bevorzugt die Original-URL uebergeben (civitai.com/api/...):
  // signierte CDN-Links laufen nach kurzer Zeit ab und taugen nicht zum
  // Fortsetzen nach Tagen. Nur wenn die Original-URL nicht passt, die
  // End-URL nehmen.
  const sendUrl = (url && matches(url, cfg.patterns)) ? url : (finalUrl || url);

  const endpoint = "http://127.0.0.1:" + cfg.port + "/add";
  let ok = false;
  try {
    const resp = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: sendUrl,
        referrer: referrer,
        filename: item.filename || ""
      })
    });
    ok = resp.ok;
  } catch (e) {
    ok = false;
  }

  if (ok) {
    // An PersistDL uebergeben -> Browser-Download stoppen und aus der
    // Download-Liste des Browsers entfernen (loescht auch die
    // angefangene .crdownload-Datei).
    try { await chrome.downloads.cancel(item.id); } catch (e) {}
    try { await chrome.downloads.erase({ id: item.id }); } catch (e) {}
    await notify("Abgefangen", "An PersistDL uebergeben:\n" + shortUrl(sendUrl));
  } else {
    // Tool nicht erreichbar / lehnte ab -> Browser-Download fortsetzen.
    if (paused) {
      try { await chrome.downloads.resume(item.id); } catch (e) {}
    }
    await notify("Tool nicht erreichbar",
      "PersistDL laeuft nicht oder Port stimmt nicht. Der Browser " +
      "laedt die Datei selbst. (Port " + cfg.port + ")");
  }
});

function shortUrl(url) {
  try {
    const u = new URL(url);
    return u.hostname + u.pathname.slice(0, 60);
  } catch (e) {
    return String(url).slice(0, 70);
  }
}

// Erlaubt der Popup-/Options-Seite, die Verbindung zum Tool zu pruefen.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "ping") {
    (async () => {
      const cfg = await getCfg();
      try {
        const resp = await fetch("http://127.0.0.1:" + cfg.port + "/ping",
          { method: "GET" });
        const data = await resp.json().catch(() => ({}));
        sendResponse({ ok: resp.ok, data, port: cfg.port });
      } catch (e) {
        sendResponse({ ok: false, error: String(e), port: cfg.port });
      }
    })();
    return true; // asynchrone Antwort
  }
});
