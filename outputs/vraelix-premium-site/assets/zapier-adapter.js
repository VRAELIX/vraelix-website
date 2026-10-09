(function (root) {
  "use strict";
  const validHook = (value) => {
    try {
      const url = new URL(value);
      const parts = url.pathname.split("/").filter(Boolean);
      return url.protocol === "https:" && url.hostname === "hooks.zapier.com" &&
        !url.username && !url.password && !url.search && !url.hash && parts.length === 4 &&
        parts[0] === "hooks" && parts[1] === "catch" &&
        parts.slice(2).every((part) => /^[A-Za-z0-9_-]+$/.test(part));
    } catch (_) { return false; }
  };

  async function submitEnquiry(payload, options) {
    const config = root.VRAELIX_CONFIG || {};
    const hookUrl = typeof config.zapierWebhookUrl === "string" && validHook(config.zapierWebhookUrl)
      ? config.zapierWebhookUrl : "";
    if (!hookUrl) throw new Error("submission_unavailable");
    const response = await fetch(hookUrl, {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      cache: "no-store",
      body: JSON.stringify(payload),
      signal: options && options.signal
    });
    if (!response.ok) throw new Error("submission_failed");
    return { success: true, submitted_at: payload.submitted_at };
  }

  root.VRAELIX_ZAPIER_ADAPTER = { submitEnquiry };
})(window);
