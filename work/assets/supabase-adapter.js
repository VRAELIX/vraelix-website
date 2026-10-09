(function (root) {
  "use strict";
  const API_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
  let turnstileLoad;
  let widgetId = null;
  let pendingToken = null;

  function loadTurnstile() {
    if (root.turnstile) return Promise.resolve(root.turnstile);
    if (turnstileLoad) return turnstileLoad;
    turnstileLoad = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = API_URL;
      script.async = true;
      script.defer = true;
      script.dataset.vraelixTurnstile = "true";
      script.onload = () => root.turnstile ? resolve(root.turnstile) : reject(new Error("turnstile_unavailable"));
      script.onerror = () => reject(new Error("turnstile_unavailable"));
      document.head.append(script);
    }).catch((error) => {
      turnstileLoad = null;
      throw error;
    });
    return turnstileLoad;
  }

  async function ensureWidget() {
    const config = root.VRAELIX_CONFIG || {};
    if (!config.turnstileSiteKey) throw new Error("protection_unavailable");
    if (widgetId !== null) return root.turnstile;
    const container = document.querySelector("[data-turnstile-widget]");
    if (!container) throw new Error("protection_unavailable");
    const turnstile = await loadTurnstile();
    widgetId = turnstile.render(container, {
      sitekey: config.turnstileSiteKey,
      action: "vraelix_enquiry",
      theme: "light",
      execution: "execute",
      appearance: "interaction-only",
      callback(token) {
        if (!pendingToken) return;
        const pending = pendingToken;
        pendingToken = null;
        clearTimeout(pending.timeout);
        pending.resolve(token);
      },
      "error-callback"() {
        rejectPendingToken();
      },
      "expired-callback"() {
        rejectPendingToken();
      },
      "timeout-callback"() {
        rejectPendingToken();
      }
    });
    return turnstile;
  }

  function rejectPendingToken() {
    if (!pendingToken) return;
    const pending = pendingToken;
    pendingToken = null;
    clearTimeout(pending.timeout);
    pending.reject(new Error("protection_failed"));
  }

  async function getTurnstileToken() {
    const turnstile = await ensureWidget();
    if (pendingToken) throw new Error("protection_in_progress");
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        if (pendingToken) {
          pendingToken = null;
          reject(new Error("protection_timeout"));
        }
      }, 45000);
      pendingToken = { resolve, reject, timeout };
      try {
        turnstile.execute(widgetId);
      } catch (_) {
        rejectPendingToken();
      }
    });
  }

  function resetTurnstile() {
    rejectPendingToken();
    if (widgetId !== null && root.turnstile) {
      try { root.turnstile.reset(widgetId); } catch (_) {}
    }
  }

  async function submitEnquiry(payload, options) {
    const config = root.VRAELIX_CONFIG || {};
    if (!config.supabaseUrl || !config.supabasePublishableKey || !options || !options.turnstileToken) {
      throw new Error("submission_unavailable");
    }
    const response = await fetch(config.supabaseUrl + "/functions/v1/submit-enquiry", {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      headers: {
        apikey: config.supabasePublishableKey,
        "content-type": "application/json"
      },
      body: JSON.stringify({ ...payload, turnstile_token: options.turnstileToken }),
      signal: options.signal
    });
    let result = null;
    try { result = await response.json(); } catch (_) {}
    if (!response.ok || !result || result.success !== true || typeof result.submitted_at !== "string") {
      throw new Error("submission_failed");
    }
    return { success: true, submitted_at: result.submitted_at };
  }

  root.VRAELIX_SUPABASE_ADAPTER = { getTurnstileToken, resetTurnstile, submitEnquiry };
})(window);
