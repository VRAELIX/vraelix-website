(function (root) {
  "use strict";
  async function submitEnquiry(payload, options) {
    const config = root.VRAELIX_CONFIG || {};
    if (config.enquiryBackend === "supabase") {
      const adapter = root.VRAELIX_SUPABASE_ADAPTER;
      if (!adapter) throw new Error("submission_unavailable");
      return adapter.submitEnquiry(payload, options || {});
    }
    const adapter = root.VRAELIX_ZAPIER_ADAPTER;
    if (!adapter) throw new Error("submission_unavailable");
    return adapter.submitEnquiry(payload, options || {});
  }
  root.VRAELIX_ENQUIRY = { submitEnquiry };
})(window);
