(function () {
  "use strict";
  const config = window.VRAELIX_CONFIG || {};
  const sitePath = (path) => {
    const base = typeof config.siteBasePath === "string" ? config.siteBasePath.replace(/\/$/, "") : "";
    const route = String(path || "/").startsWith("/") ? String(path || "/") : "/" + String(path || "");
    return base + route || "/";
  };
  document.documentElement.classList.add("has-js");

  const video = document.querySelector(".hero__video");
  if (video) {
    video.muted = true;
    video.defaultMuted = true;
    video.volume = 0;
    const source = video.querySelector("[data-responsive-video]");
    const fallback = video.querySelector("[data-responsive-video-fallback]");
    if (source) {
      const breakpoint = window.matchMedia("(max-width: 600px)");
      const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
      if (reducedMotion.matches) {
        video.removeAttribute("autoplay");
        video.pause();
      }
      const selectVideo = () => {
        const mobile = breakpoint.matches;
        const selected = [
          [source, mobile ? source.dataset.mobile : source.dataset.desktop],
          [fallback, fallback && (mobile ? fallback.dataset.mobile : fallback.dataset.desktop)]
        ].filter(([item, path]) => item && path);
        if (!selected.some(([item, path]) => item.getAttribute("src") !== path)) return;
        const shouldPlay = !reducedMotion.matches && (video.autoplay || !video.paused);
        selected.forEach(([item, path]) => {
          item.src = path;
          item.type = path.toLowerCase().endsWith(".mp4") ? "video/mp4" : "video/webm";
        });
        video.load();
        if (shouldPlay) video.play().catch(() => {});
      };
      selectVideo();
      if (breakpoint.addEventListener) breakpoint.addEventListener("change", selectVideo);
      else if (breakpoint.addListener) breakpoint.addListener(selectVideo);
      const handleMotionPreference = (event) => {
        if (event.matches) {
          video.pause();
          video.removeAttribute("autoplay");
        } else {
          video.setAttribute("autoplay", "");
          video.play().catch(() => {});
        }
      };
      if (reducedMotion.addEventListener) reducedMotion.addEventListener("change", handleMotionPreference);
      else if (reducedMotion.addListener) reducedMotion.addListener(handleMotionPreference);
    }
  }

  const header = document.querySelector("[data-site-header]");
  const updateHeader = () => {
    if (!header) return;
    header.classList.toggle("is-scrolled", document.body.dataset.route !== "/" || window.scrollY > 30);
  };
  updateHeader();
  let scrollQueued = false;
  window.addEventListener("scroll", () => {
    if (scrollQueued) return;
    scrollQueued = true;
    requestAnimationFrame(() => {
      updateHeader();
      scrollQueued = false;
    });
  }, { passive: true });

  const menuButton = document.querySelector("[data-menu-toggle]");
  const nav = document.querySelector("[data-primary-nav]");
  let menuScrollPosition = 0;
  const closeMenu = (restoreFocus = true) => {
    if (!menuButton || !nav) return;
    const wasOpen = document.body.classList.contains("menu-open");
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "Open navigation");
    nav.classList.remove("is-open");
    document.body.classList.remove("menu-open");
    document.body.style.removeProperty("--menu-scroll-top");
    if (wasOpen) {
      document.querySelector("#main")?.removeAttribute("inert");
      document.querySelector(".site-footer")?.removeAttribute("inert");
      window.scrollTo(0, menuScrollPosition);
      if (restoreFocus && window.matchMedia("(max-width: 850px)").matches) {
        menuButton.focus({ preventScroll: true });
      }
    }
    updateHeader();
  };
  if (menuButton && nav) {
    menuButton.addEventListener("click", () => {
      const open = menuButton.getAttribute("aria-expanded") !== "true";
      if (!open) {
        closeMenu();
        return;
      }
      menuScrollPosition = window.scrollY;
      document.body.style.setProperty("--menu-scroll-top", `-${menuScrollPosition}px`);
      menuButton.setAttribute("aria-expanded", String(open));
      menuButton.setAttribute("aria-label", "Close navigation");
      nav.classList.add("is-open");
      document.querySelector("#main")?.setAttribute("inert", "");
      document.querySelector(".site-footer")?.setAttribute("inert", "");
      document.body.classList.add("menu-open");
      if (header) header.classList.add("is-scrolled");
      menuButton.focus({ preventScroll: true });
    });
    nav.addEventListener("click", (event) => {
      if (event.target.closest("a")) closeMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (!document.body.classList.contains("menu-open")) return;
      if (event.key === "Escape") {
        closeMenu();
        return;
      }
      if (event.key !== "Tab") return;
      const links = nav.querySelectorAll("a[href]");
      const first = links[0];
      const last = links[links.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && (document.activeElement === first || document.activeElement === menuButton)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        menuButton.focus();
      }
    });
    const desktopMenu = window.matchMedia("(min-width: 851px)");
    if (desktopMenu.addEventListener) desktopMenu.addEventListener("change", (event) => { if (event.matches) closeMenu(false); });
    else if (desktopMenu.addListener) desktopMenu.addListener((event) => { if (event.matches) closeMenu(false); });
  }

  document.querySelectorAll("[data-year]").forEach((node) => {
    node.textContent = String(new Date().getFullYear());
  });

  const consentPanel = document.querySelector("[data-consent-panel]");
  if (consentPanel) {
    const consentKey = "vraelix-cookie-consent-v2";
    const measurementId = typeof config.ga4MeasurementId === "string" && /^G-[A-Z0-9]{5,20}$/.test(config.ga4MeasurementId)
      ? config.ga4MeasurementId : "";
    const manageButton = consentPanel.querySelector("[data-consent-manage]");
    const management = consentPanel.querySelector("[data-consent-management]");
    const saveButton = consentPanel.querySelector("[data-consent-save]");
    const analyticsInput = consentPanel.querySelector("[data-consent-analytics]");
    let externalTrigger = null;
    let savedChoice = null;
    let manuallyOpened = false;
    let heroObserver = null;
    try {
      const stored = localStorage.getItem(consentKey);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed && parsed.version === 2 && typeof parsed.analytics === "boolean") {
          savedChoice = { analytics: Boolean(measurementId && parsed.analytics) };
        }
      } else if (localStorage.getItem("vraelix-cookie-consent-v1") === "essential-only-v1") {
        savedChoice = { analytics: false };
        localStorage.setItem(consentKey, JSON.stringify({ version: 2, analytics: false }));
      }
    } catch (_) {}
    if (analyticsInput) analyticsInput.checked = Boolean(savedChoice && savedChoice.analytics);

    const applyAnalytics = (enabled) => {
      if (!measurementId) return;
      const disabledFlag = "ga-disable-" + measurementId;
      if (!enabled) {
        window[disabledFlag] = true;
        if (typeof window.gtag === "function") {
          window.gtag("consent", "update", {
            analytics_storage: "denied",
            ad_storage: "denied",
            ad_user_data: "denied",
            ad_personalization: "denied"
          });
        }
        return;
      }
      window[disabledFlag] = false;
      if (window.__vraelixGa4Initialized) {
        if (typeof window.gtag === "function") window.gtag("consent", "update", { analytics_storage: "granted" });
        return;
      }
      const dataLayer = window.dataLayer = window.dataLayer || [];
      window.gtag = window.gtag || function () { dataLayer.push(arguments); };
      window.gtag("consent", "default", {
        analytics_storage: "denied",
        ad_storage: "denied",
        ad_user_data: "denied",
        ad_personalization: "denied"
      });
      window.gtag("consent", "update", { analytics_storage: "granted" });
      window.gtag("js", new Date());
      window.gtag("config", measurementId, { send_page_view: true });
      window.__vraelixGa4Initialized = true;
      if (!document.querySelector("script[data-vraelix-ga4]")) {
        const analyticsScript = document.createElement("script");
        analyticsScript.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(measurementId);
        analyticsScript.async = true;
        analyticsScript.dataset.vraelixGa4 = "true";
        document.head.append(analyticsScript);
      }
    };
    if (savedChoice) applyAnalytics(savedChoice.analytics);

    if (!savedChoice) {
      const homeHero = document.body.dataset.route === "/" && document.querySelector(".hero");
      if (homeHero && "IntersectionObserver" in window) {
        heroObserver = new IntersectionObserver((entries) => {
          if (savedChoice || manuallyOpened) return;
          consentPanel.hidden = entries[0].isIntersecting;
        });
        heroObserver.observe(homeHero);
      } else {
        consentPanel.hidden = false;
      }
    }

    const showManagement = (show, moveFocus) => {
      management.hidden = !show;
      consentPanel.classList.toggle("is-managing", show);
      manageButton.setAttribute("aria-expanded", String(show));
      if (analyticsInput) analyticsInput.checked = Boolean(savedChoice && savedChoice.analytics);
      if (moveFocus) (show ? saveButton : manageButton).focus({ preventScroll: true });
    };
    const closePanel = () => {
      consentPanel.hidden = true;
      showManagement(false, false);
      if (externalTrigger) {
        externalTrigger.focus({ preventScroll: true });
        externalTrigger = null;
      }
    };
    const savePreference = (analytics) => {
      const choice = { version: 2, analytics: Boolean(measurementId && analytics) };
      try { localStorage.setItem(consentKey, JSON.stringify(choice)); } catch (_) {}
      savedChoice = { analytics: choice.analytics };
      applyAnalytics(choice.analytics);
      closePanel();
    };

    consentPanel.querySelector("[data-consent-accept]").addEventListener("click", () => savePreference(Boolean(measurementId)));
    saveButton.addEventListener("click", () => savePreference(Boolean(analyticsInput && analyticsInput.checked)));
    manageButton.addEventListener("click", () => showManagement(true, true));
    consentPanel.querySelector("[data-consent-back]").addEventListener("click", () => showManagement(false, true));
    document.querySelectorAll("[data-consent-open]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        externalTrigger = trigger;
        manuallyOpened = true;
        consentPanel.hidden = false;
        showManagement(true, true);
      });
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !consentPanel.hidden && !management.hidden) {
        event.preventDefault();
        showManagement(false, true);
      }
    });
  }

  const icons = {
    linkedin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9v10M5 5v.1M9 19v-6a4 4 0 0 1 8 0v6M9 9v10"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="4"/><circle cx="12" cy="12" r="4"/><path d="M17.5 6.8h.01"/></svg>'
  };
  const contacts = [];
  if (config.email) contacts.push({ key: "email", label: "Email", url: "mailto:" + config.email, raw: config.email });
  if (config.whatsapp) {
    const digits = String(config.whatsapp).replace(/\D/g, "");
    if (digits) contacts.push({ key: "whatsapp", label: "WhatsApp", url: "https://wa.me/" + digits });
  }
  if (config.instagram) contacts.push({ key: "instagram", label: "Instagram", url: config.instagram });
  if (config.linkedin) contacts.push({ key: "linkedin", label: "LinkedIn", url: config.linkedin });

  const makeSocialLink = (item) => {
    const link = document.createElement("a");
    link.className = "social-link";
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.setAttribute("aria-label", "VRAELIX on " + item.label);
    link.title = "VRAELIX on " + item.label;
    link.innerHTML = icons[item.key];
    return link;
  };
  document.querySelectorAll("[data-social-links]").forEach((container) => {
    contacts.filter((item) => item.key === "instagram" || item.key === "linkedin")
      .forEach((item) => container.append(makeSocialLink(item)));
  });
  document.querySelectorAll("[data-contact-links]").forEach((container) => {
    container.replaceChildren();
    contacts.forEach((item) => {
      const link = document.createElement("a");
      link.href = item.url;
      if (item.url.startsWith("https://")) {
        link.target = "_blank";
        link.rel = "noopener noreferrer";
      }
      const label = document.createElement("span");
      label.textContent = item.label + (item.raw && item.key === "email" ? " · " + item.raw : "");
      const arrow = document.createElement("span");
      arrow.textContent = "↗";
      arrow.setAttribute("aria-hidden", "true");
      link.append(label, arrow);
      container.append(link);
    });
  });

  const cleanFormValue = (value, maxLength, multiline = false) => {
    let text = String(value ?? "").replace(/\r\n?/g, "\n");
    text = multiline
      ? text.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, "")
      : text.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ");
    return text.trim().slice(0, maxLength);
  };
  const labels = [
    ["full_name", "Full name", 100], ["email", "Email", 254], ["phone_number", "Phone number", 32],
    ["company", "Company / business", 160], ["service", "Service required", 100],
    ["project_description", "Project description", 2400, true], ["budget", "Budget range", 120],
    ["timeline", "Timeline", 120], ["contact_method", "Preferred contact method", 40]
  ];
  const contactMethods = ["Email", "WhatsApp", "Instagram / Social", "Other"];
  const form = document.querySelector("[data-project-form]");
  if (form) {
    form.noValidate = true;
    const feedback = form.querySelector("[data-form-feedback]");
    const submitButton = form.querySelector('button[type="submit"]');
    const activeBackend = config.enquiryBackend === "supabase" ? "supabase" : "zapier";
    const backendReady = activeBackend === "supabase"
      ? Boolean(config.supabaseUrl && config.supabasePublishableKey && config.turnstileSiteKey)
      : Boolean(config.zapierWebhookUrl);
    const turnstileSlot = form.querySelector("[data-turnstile-slot]");
    if (activeBackend === "supabase" && backendReady && turnstileSlot) turnstileSlot.hidden = false;
    const field = (name) => form.elements.namedItem(name);
    const validationNames = ["full_name", "email", "phone_number", "service", "project_description", "contact_method"];
    const phoneIsValid = (value) => {
      const phone = cleanFormValue(value, 32);
      const digits = phone.replace(/\D/g, "");
      return /^\+?[0-9][0-9\s().-]*$/.test(phone) && digits.length >= 7 && digits.length <= 15;
    };
    const fieldError = (name) => {
      const input = field(name);
      const value = cleanFormValue(input ? input.value : "", labels.find((item) => item[0] === name)?.[2] || 2400, name === "project_description");
      if (name === "full_name" && value.length < 2) return "Enter your name (at least 2 characters).";
      if (name === "email" && (!input || !input.checkValidity())) return "Enter a valid email address.";
      if (name === "phone_number" && !phoneIsValid(value)) return "Enter a phone number with 7–15 digits.";
      if (name === "service" && (!Array.isArray(config.services) || !config.services.includes(value))) return "Choose a listed service.";
      if (name === "project_description" && value.length < 10) return "Add at least 10 characters about your project.";
      if (name === "contact_method" && !contactMethods.includes(value)) return "Choose a preferred contact method.";
      return "";
    };
    const setFieldError = (name, message) => {
      const input = field(name);
      const error = form.querySelector('[data-field-error="' + name + '"]');
      if (!input || !error) return;
      input.setAttribute("aria-invalid", message ? "true" : "false");
      error.textContent = message;
      error.hidden = !message;
    };
    labels.forEach(([name]) => {
      const input = field(name);
      if (input) {
        input.addEventListener("input", () => {
          if (input.getAttribute("aria-invalid") === "true") {
            setFieldError(name, fieldError(name));
            if (feedback && feedback.dataset.state === "error" && !form.querySelector('[aria-invalid="true"]')) {
              feedback.textContent = "";
              delete feedback.dataset.state;
            }
          }
        });
        input.addEventListener("change", () => {
          if (input.getAttribute("aria-invalid") === "true") {
            setFieldError(name, fieldError(name));
            if (feedback && feedback.dataset.state === "error" && !form.querySelector('[aria-invalid="true"]')) {
              feedback.textContent = "";
              delete feedback.dataset.state;
            }
          }
        });
      }
    });
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (form.dataset.submitting === "true" || form.dataset.submitted === "true") return;
      const invalid = validationNames.filter((name) => {
        const message = fieldError(name);
        setFieldError(name, message);
        return Boolean(message);
      });
      if (invalid.length) {
        if (feedback) {
          feedback.textContent = "Please review the highlighted fields and try again.";
          feedback.dataset.state = "error";
        }
        const firstInvalid = field(invalid[0]);
        if (firstInvalid) firstInvalid.focus();
        return;
      }
      if (!backendReady) {
        if (feedback) {
          feedback.textContent = "This form is not ready to send yet. Your details are still here; please contact VRAELIX by email or try again later.";
          feedback.dataset.state = "error";
        }
        return;
      }
      const payload = {
        full_name: cleanFormValue(field("full_name").value, 100),
        email: cleanFormValue(field("email").value, 254),
        phone_number: cleanFormValue(field("phone_number").value, 32),
        company: cleanFormValue(field("company").value, 160),
        service: cleanFormValue(field("service").value, 100),
        project_description: cleanFormValue(field("project_description").value, 2400, true),
        budget: cleanFormValue(field("budget").value, 120),
        timeline: cleanFormValue(field("timeline").value, 120),
        contact_method: cleanFormValue(field("contact_method").value, 40),
        source: "VRAELIX Website",
        submitted_at: new Date().toISOString()
      };
      field("full_name").value = payload.full_name;
      field("email").value = payload.email;
      field("phone_number").value = payload.phone_number;
      field("project_description").value = payload.project_description;
      field("source").value = payload.source;
      field("submitted_at").value = payload.submitted_at;
      form.dataset.submitting = "true";
      form.setAttribute("aria-busy", "true");
      if (feedback) {
        feedback.textContent = "Sending your enquiry…";
        feedback.dataset.state = "sending";
      }
      const originalButtonMarkup = submitButton ? submitButton.innerHTML : "";
      if (submitButton) submitButton.disabled = true;
      if (submitButton) submitButton.textContent = "Sending enquiry…";
      let controller = null;
      let timeout = null;
      let receipt = null;
      try {
        let turnstileToken = "";
        if (activeBackend === "supabase") {
          turnstileToken = await window.VRAELIX_SUPABASE_ADAPTER.getTurnstileToken();
        }
        controller = new AbortController();
        timeout = window.setTimeout(() => controller.abort(), 20000);
        receipt = await window.VRAELIX_ENQUIRY.submitEnquiry(payload, {
          signal: controller.signal,
          turnstileToken
        });
        if (!receipt || receipt.success !== true || Number.isNaN(Date.parse(receipt.submitted_at))) {
          throw new Error("submission_failed");
        }
      } catch (_) {
        if (timeout !== null) window.clearTimeout(timeout);
        if (activeBackend === "supabase" && window.VRAELIX_SUPABASE_ADAPTER) {
          window.VRAELIX_SUPABASE_ADAPTER.resetTurnstile();
        }
        if (feedback) {
          feedback.textContent = "Something went wrong while sending your enquiry. Your information is still here — please try again.";
          feedback.dataset.state = "error";
        }
        form.dataset.submitting = "false";
        form.removeAttribute("aria-busy");
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.innerHTML = originalButtonMarkup;
        }
        return;
      }
      if (timeout !== null) window.clearTimeout(timeout);
      payload.submitted_at = receipt.submitted_at;
      field("submitted_at").value = receipt.submitted_at;
      if (feedback) {
        feedback.textContent = "Thank you. Your project enquiry has been received.";
        feedback.dataset.state = "success";
      }
      let receiptSaved = false;
      try {
        sessionStorage.setItem("vraelix-project-brief", JSON.stringify(payload));
        sessionStorage.setItem("vraelix-project-brief-confirmed", "true");
        receiptSaved = true;
      } catch (_) {
        try {
          sessionStorage.removeItem("vraelix-project-brief");
          sessionStorage.removeItem("vraelix-project-brief-confirmed");
        } catch (_) {}
      }
      form.dataset.submitted = "true";
      form.removeAttribute("aria-busy");
      if (receiptSaved) {
        form.reset();
        window.location.assign(sitePath("/thank-you/"));
      } else if (feedback) {
        feedback.textContent = "Your enquiry has been received. This browser could not open the confirmation page, so your entered details remain here.";
      }
    });
    if (backendReady && submitButton) {
      submitButton.disabled = false;
      if (feedback) feedback.textContent = "";
    }
  }

  let brief = null;
  let briefConfirmed = false;
  try {
    const stored = JSON.parse(sessionStorage.getItem("vraelix-project-brief") || "null");
    const wasConfirmed = sessionStorage.getItem("vraelix-project-brief-confirmed") === "true";
    if (stored && typeof stored === "object" && !Array.isArray(stored) && wasConfirmed && stored.source === "VRAELIX Website" && !Number.isNaN(Date.parse(stored.submitted_at))) {
      brief = Object.fromEntries(labels.map(([key, label, limit, multiline]) => [key,
        typeof stored[key] === "string" ? cleanFormValue(stored[key], limit, Boolean(multiline)) : ""]));
      if (!contactMethods.includes(brief.contact_method)) brief.contact_method = "";
      if (!Array.isArray(config.services) || !config.services.includes(brief.service)) brief.service = "";
      briefConfirmed = true;
    }
  } catch (_) {}
  const briefText = () => brief
    ? labels.filter((pair) => brief[pair[0]]).map((pair) => pair[1] + ": " + brief[pair[0]]).join("\n")
    : "";
  const summary = document.querySelector("[data-brief-summary]");
  if (summary && brief) {
    const dl = document.createElement("dl");
    labels.filter((pair) => brief[pair[0]]).forEach((pair) => {
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = pair[1];
      dd.textContent = brief[pair[0]];
      dl.append(dt, dd);
    });
    summary.replaceChildren(dl);
    const title = document.querySelector("[data-thanks-title]");
    if (title) title.textContent = brief.full_name
      ? "Thank you, " + brief.full_name + ". Your enquiry has been received."
      : "Thank you. Your enquiry has been received.";
    const note = document.querySelector("[data-thanks-note]");
    if (note) note.textContent = "Your project enquiry was received by VRAELIX. This copy is available in this browser tab for your records.";
    const empty = document.querySelector("[data-thanks-empty]");
    if (empty) empty.hidden = true;
    const copy = document.querySelector("[data-copy-brief]");
    if (copy) copy.hidden = false;
  }
  const copyButton = document.querySelector("[data-copy-brief]");
  if (copyButton && brief) {
    copyButton.addEventListener("click", async () => {
      const text = briefText();
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
      } catch (_) {
        const helper = document.createElement("textarea");
        helper.value = text;
        helper.className = "clipboard-fallback";
        document.body.append(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
      }
      copyButton.textContent = "Copied";
    });
  }
  const actions = document.querySelector("[data-thanks-actions]");
  if (actions && briefConfirmed) {
    const link = document.createElement("a");
    link.href = sitePath("/contact/");
    link.textContent = "Contact VRAELIX ↗";
    actions.replaceChildren(link);
  }

  const revealItems = document.querySelectorAll(".section-heading,.intro-grid,.founder-grid,.steps-grid,.insight-card,.process-row,.principle-grid article,.faq-item,.service-main,.contact-grid,.quote-form-wrap");
  if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const observer = new IntersectionObserver((entries, current) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          current.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -35px 0px" });
    revealItems.forEach((element) => {
      element.setAttribute("data-reveal", "");
      observer.observe(element);
    });
  }
})();
