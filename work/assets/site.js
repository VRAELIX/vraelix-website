(function () {
  "use strict";
  const config = window.VRAELIX_CONFIG || {};
  const sitePath = (path) => {
    const base = typeof config.siteBasePath === "string" ? config.siteBasePath.replace(/\/$/, "") : "";
    const route = String(path || "/").startsWith("/") ? String(path || "/") : "/" + String(path || "");
    return base + route || "/";
  };
  const showBrandIntro = () => {
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return Promise.resolve();
    let shouldShow = true;
    try {
      if (sessionStorage.getItem("vraelix-brand-intro-shown-v1") === "true") shouldShow = false;
      else sessionStorage.setItem("vraelix-brand-intro-shown-v1", "true");
    } catch (_) {}
    if (!shouldShow) return Promise.resolve();
    return new Promise((resolve) => {
      const intro = document.createElement("div");
      intro.className = "vraelix-brand-intro";
      intro.setAttribute("aria-hidden", "true");
      const logo = document.createElement("img");
      logo.src = sitePath("/assets/brand/vraelix-logo-white.png");
      logo.alt = "";
      logo.width = 1490;
      logo.height = 613;
      intro.append(logo);
      let finished = false;
      let leaving = false;
      let holdTimer = null;
      let exitTimer = null;
      const removeIntro = () => {
        if (finished) return;
        finished = true;
        if (holdTimer !== null) window.clearTimeout(holdTimer);
        if (exitTimer !== null) window.clearTimeout(exitTimer);
        document.removeEventListener("keydown", skipIntro);
        intro.remove();
        resolve();
      };
      const finishIntro = () => {
        if (finished || leaving) return;
        leaving = true;
        intro.classList.add("is-leaving");
        exitTimer = window.setTimeout(removeIntro, 450);
      };
      const skipIntro = () => finishIntro();
      intro.addEventListener("click", skipIntro);
      document.addEventListener("keydown", skipIntro);
      document.body.append(intro);
      holdTimer = window.setTimeout(finishIntro, 1750);
    });
  };
  const brandIntroFinished = showBrandIntro();
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
      let heroIsVisible = true;
      const syncVideoPlayback = () => {
        if (reducedMotion.matches || !heroIsVisible) {
          video.pause();
          return;
        }
        video.play().catch(() => {});
      };
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
        const shouldPlay = !reducedMotion.matches && heroIsVisible && (video.autoplay || !video.paused);
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
          video.removeAttribute("autoplay");
        } else {
          video.setAttribute("autoplay", "");
        }
        syncVideoPlayback();
      };
      if (reducedMotion.addEventListener) reducedMotion.addEventListener("change", handleMotionPreference);
      else if (reducedMotion.addListener) reducedMotion.addListener(handleMotionPreference);
      const hero = video.closest(".hero");
      if (hero && "IntersectionObserver" in window) {
        const videoVisibilityObserver = new IntersectionObserver((entries) => {
          heroIsVisible = entries.some((entry) => entry.isIntersecting);
          syncVideoPlayback();
        }, { threshold: 0.05 });
        videoVisibilityObserver.observe(hero);
      }
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
    const noticeVisitKey = "vraelix-privacy-notice-acknowledged-v1";
    const measurementId = typeof config.ga4MeasurementId === "string" && /^G-[A-Z0-9]{5,20}$/.test(config.ga4MeasurementId)
      ? config.ga4MeasurementId : "";
    const manageButton = consentPanel.querySelector("[data-consent-manage]");
    const management = consentPanel.querySelector("[data-consent-management]");
    const saveButton = consentPanel.querySelector("[data-consent-save]");
    const closeButton = consentPanel.querySelector("[data-consent-close]");
    const analyticsInput = consentPanel.querySelector("[data-consent-analytics]");
    let externalTrigger = null;
    let returnFocus = null;
    let savedChoice = null;
    let autoNoticePending = true;
    let autoNoticeVisible = false;
    let manualNoticeOpen = false;
    try {
      autoNoticePending = sessionStorage.getItem(noticeVisitKey) !== "true";
    } catch (_) {}
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


    const showManagement = (show, moveFocus) => {
      management.hidden = !show;
      consentPanel.classList.toggle("is-managing", show);
      manageButton.setAttribute("aria-expanded", String(show));
      if (analyticsInput) analyticsInput.checked = Boolean(savedChoice && savedChoice.analytics);
      if (moveFocus) (show ? saveButton : manageButton).focus({ preventScroll: true });
    };
    const acknowledgeNotice = () => {
      autoNoticePending = false;
      try { sessionStorage.setItem(noticeVisitKey, "true"); } catch (_) {}
    };
    const updateAutoNotice = () => {
      if (manualNoticeOpen) {
        return;
      }
      if (autoNoticePending) {
        consentPanel.hidden = false;
        autoNoticeVisible = true;
      } else if (autoNoticeVisible) {
        consentPanel.hidden = true;
        autoNoticeVisible = false;
      }
    };
    const closePanel = () => {
      consentPanel.hidden = true;
      showManagement(false, false);
      manualNoticeOpen = false;
      autoNoticeVisible = false;
      acknowledgeNotice();
      const target = externalTrigger || (consentPanel.contains(document.activeElement) ? returnFocus : null);
      externalTrigger = null;
      returnFocus = null;
      if (target && target.isConnected && typeof target.focus === "function") target.focus({ preventScroll: true });
    };
    const savePreference = (analytics) => {
      const choice = { version: 2, analytics: Boolean(measurementId && analytics) };
      try { localStorage.setItem(consentKey, JSON.stringify(choice)); } catch (_) {}
      savedChoice = { analytics: choice.analytics };
      applyAnalytics(choice.analytics);
      closePanel();
    };

    consentPanel.addEventListener("focusin", (event) => {
      if (event.relatedTarget && !consentPanel.contains(event.relatedTarget)) returnFocus = event.relatedTarget;
    });
    consentPanel.querySelector("[data-consent-accept]").addEventListener("click", closePanel);
    saveButton.addEventListener("click", () => savePreference(Boolean(analyticsInput && analyticsInput.checked)));
    manageButton.addEventListener("click", () => showManagement(true, true));
    consentPanel.querySelector("[data-consent-back]").addEventListener("click", () => showManagement(false, true));
    document.querySelectorAll("[data-consent-open]").forEach((trigger) => {
      trigger.addEventListener("click", () => {
        externalTrigger = trigger;
        manualNoticeOpen = true;
        autoNoticeVisible = false;
        consentPanel.hidden = false;
        showManagement(true, false);
        window.requestAnimationFrame(() => {
          const panelHeight = consentPanel.getBoundingClientRect().height;
          if (trigger.closest(".site-footer")) {
            window.scrollBy({ top: Math.ceil(panelHeight + 24), behavior: "auto" });
          }
          saveButton.focus({ preventScroll: true });
        });
      });
    });
    closeButton.addEventListener("click", closePanel);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !consentPanel.hidden) {
        event.preventDefault();
        closePanel();
      }
    });
    brandIntroFinished.then(updateAutoNotice);
  }
  const icons = {
    linkedin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M20.45 20.45h-3.56v-5.57c0-1.33-.03-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.34 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12ZM3.56 9h3.56v11.45H3.56V9Z"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="3.5" width="17" height="17" rx="5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="17.6" cy="6.6" r="1.1" fill="currentColor"/></svg>'
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
    const stagingTestMode = activeBackend === "supabase" && config.enquiryStagingTestMode === true;
    const backendReady = (config.enquiryBackendVerified === true || stagingTestMode) && (activeBackend === "supabase"
      ? Boolean(config.supabaseUrl && config.supabasePublishableKey && config.turnstileSiteKey)
      : Boolean(config.zapierWebhookUrl));
    const turnstileSlot = form.querySelector("[data-turnstile-slot]");
    if (activeBackend === "supabase" && backendReady && turnstileSlot) turnstileSlot.hidden = false;
    const showUnavailableMessage = () => {
      if (submitButton) submitButton.disabled = true;
      if (!feedback) return;
      feedback.replaceChildren(document.createTextNode("Online enquiries cannot currently be submitted. Your details will not be sent. Please "));
      const email = typeof config.email === "string" ? config.email.trim() : "";
      if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
        const emailLink = document.createElement("a");
        emailLink.href = `mailto:${email}`;
        emailLink.textContent = "email VRAELIX";
        feedback.append(emailLink, document.createTextNode(" instead."));
      } else {
        feedback.append(document.createTextNode("contact VRAELIX instead."));
      }
      feedback.dataset.state = "unavailable";
    };
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
      // Read ValidityState directly. Calling checkValidity() here dispatches
      // another `invalid` event, which re-enters this handler recursively.
      if (name === "email" && (!input || !input.validity.valid)) return "Enter a valid email address.";
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
        input.addEventListener("invalid", () => {
          setFieldError(name, fieldError(name));
          if (feedback) {
            feedback.textContent = "Please review the highlighted fields and try again.";
            feedback.dataset.state = "error";
          }
        });
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
        if (firstInvalid) {
          firstInvalid.focus();
          if (!firstInvalid.checkValidity()) firstInvalid.reportValidity();
        }
        return;
      }
      if (!backendReady) {
        showUnavailableMessage();
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
    } else if (!backendReady) {
      showUnavailableMessage();
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
    if (note) note.textContent = "Your project enquiry was received by VRAELIX. These details are shown here for your records.";
    const empty = document.querySelector("[data-thanks-empty]");
    if (empty) empty.hidden = true;
  }
  const actions = document.querySelector("[data-thanks-actions]");
  if (actions && briefConfirmed) {
    const link = document.createElement("a");
    link.href = sitePath("/contact/");
    link.textContent = "Contact VRAELIX ↗";
    actions.replaceChildren(link);
  }

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const planCards = document.querySelectorAll("[data-plan-card]");
  if (planCards.length && "IntersectionObserver" in window && !reducedMotion) {
    const planObserver = new IntersectionObserver((entries, current) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          current.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -30px 0px" });
    planCards.forEach((card, index) => {
      card.style.setProperty("--plan-stagger", `${index * 120}ms`);
      card.classList.add("plan-card-reveal");
      planObserver.observe(card);
    });
  }

  document.querySelectorAll("[data-services-slider]").forEach((slider) => {
    const track = slider.querySelector("[data-services-track]");
    const cards = Array.from(slider.querySelectorAll("[data-service-card]"));
    const previous = slider.querySelector("[data-services-prev]");
    const next = slider.querySelector("[data-services-next]");
    if (!track || !cards.length || !previous || !next) return;
    slider.classList.add("is-enhanced");
    previous.hidden = false;
    next.hidden = false;
    let centeredIndex = 0;
    let updateQueued = false;
    const updateSlider = () => {
      const trackRect = track.getBoundingClientRect();
      const center = trackRect.left + track.clientWidth / 2;
      let nearestDistance = Infinity;
      cards.forEach((card, index) => {
        const rect = card.getBoundingClientRect();
        const distance = Math.abs(rect.left + rect.width / 2 - center);
        if (distance < nearestDistance) {
          nearestDistance = distance;
          centeredIndex = index;
        }
      });
      cards.forEach((card, index) => card.classList.toggle("is-centered", index === centeredIndex));
      previous.disabled = centeredIndex <= 0;
      next.disabled = centeredIndex >= cards.length - 1;
      updateQueued = false;
    };
    const queueSliderUpdate = () => {
      if (updateQueued) return;
      updateQueued = true;
      window.requestAnimationFrame(updateSlider);
    };
    const scrollToCard = (index) => {
      const targetIndex = Math.max(0, Math.min(cards.length - 1, index));
      const target = cards[targetIndex];
      const trackRect = track.getBoundingClientRect();
      const cardRect = target.getBoundingClientRect();
      const left = track.scrollLeft + cardRect.left - trackRect.left - (track.clientWidth - cardRect.width) / 2;
      track.scrollTo({ left, behavior: reducedMotion ? "auto" : "smooth" });
    };
    previous.addEventListener("click", () => scrollToCard(centeredIndex - 1));
    next.addEventListener("click", () => scrollToCard(centeredIndex + 1));
    track.addEventListener("scroll", queueSliderUpdate, { passive: true });
    track.addEventListener("keydown", (event) => {
      if (event.target !== track || (event.key !== "ArrowLeft" && event.key !== "ArrowRight")) return;
      event.preventDefault();
      scrollToCard(centeredIndex + (event.key === "ArrowRight" ? 1 : -1));
    });
    window.addEventListener("resize", queueSliderUpdate, { passive: true });
    updateSlider();
  });

  const revealItems = document.querySelectorAll(".section-heading,.intro-grid,.split-copy,.founder-grid,.founder-story-grid,.steps-grid,.insight-card,.process-row,.principle-grid article,.faq-item,.service-main,.service-detail-grid,.contact-grid,.faq-layout,.quote-form-wrap");
  if ("IntersectionObserver" in window && !reducedMotion) {
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

    const artTargets = document.querySelectorAll(".intro-grid,.split-copy,.contact-grid,.founder-story-grid,.service-detail-grid,.faq-layout");
    const artObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => entry.target.classList.toggle("art-in-view", entry.isIntersecting));
    }, { threshold: 0, rootMargin: "100px 0px" });
    artTargets.forEach((element) => artObserver.observe(element));
  }
})();
