/**
 * Mahlatini Enquiry Form Submission Handler
 * ==========================================
 * Embeddable script that captures website enquiry forms and sends
 * them to the n8n webhook for processing → Outlook + Gemini classification.
 *
 * Usage:
 *   <script src="/widget/enquiry-form.js"
 *           data-webhook-url="https://your-domain.com/webhook/website-enquiry"
 *           data-webhook-secret="your-shared-secret"
 *           defer></script>
 *
 *   Then attach to any form:
 *     <form data-mahlatini-enquiry>
 *       <input name="name" required>
 *       <input name="email" type="email" required>
 *       ...
 *     </form>
 *
 * The script auto-binds to forms with [data-mahlatini-enquiry].
 */

(function () {
  'use strict';

  // --- Configuration ---
  const scriptTag = document.currentScript;
  const WEBHOOK_URL = scriptTag?.getAttribute('data-webhook-url') || '/webhook/website-enquiry';
  const WEBHOOK_SECRET = scriptTag?.getAttribute('data-webhook-secret') || '';

  // --- HMAC-SHA256 signing ---
  async function hmacSign(payload, secret) {
    if (!secret) return '';
    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
      'raw',
      encoder.encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    );
    const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(JSON.stringify(payload)));
    const hex = Array.from(new Uint8Array(signature))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
    return 'sha256=' + hex;
  }

  // --- Extract form data into structured payload ---
  function extractFormData(form) {
    const fd = new FormData(form);
    const raw = {};
    for (const [key, value] of fd.entries()) {
      raw[key] = value;
    }

    // Map common field names to the expected schema
    const formData = {
      name: raw.name || raw.full_name || raw.fullname || '',
      email: raw.email || raw.email_address || '',
      phone: raw.phone || raw.telephone || raw.tel || '',
      destination: raw.destination || raw.country || '',
      travel_dates: raw.travel_dates || raw.travel_date || raw.dates || raw.when || '',
      duration: raw.duration || raw.nights || '',
      party_size: {
        adults: parseInt(raw.adults || raw.pax_adults || '0') || 0,
        children: parseInt(raw.children || raw.pax_children || '0') || 0,
        children_ages: raw.children_ages
          ? raw.children_ages.split(',').map(a => parseInt(a.trim())).filter(Boolean)
          : [],
      },
      budget_range: raw.budget || raw.budget_range || '',
      experience_type: raw.experience_type
        ? raw.experience_type.split(',').map(s => s.trim())
        : (raw.experience ? [raw.experience] : []),
      special_occasion: raw.special_occasion || raw.occasion || null,
      message: raw.message || raw.comments || raw.enquiry || raw.notes || '',
      how_heard: raw.how_heard || raw.referral || '',
      newsletter_consent: raw.newsletter === 'on' || raw.newsletter === 'true' || raw.newsletter === '1',
      // Honeypot field (hidden input, should be empty)
      _hp_field: raw._hp_field || raw.website || '',
    };

    return formData;
  }

  // --- Submit enquiry ---
  async function submitEnquiry(form) {
    const formData = extractFormData(form);

    // Client-side validation
    if (!formData.name || formData.name.trim().length < 2) {
      throw new Error('Please enter your name.');
    }
    if (!formData.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      throw new Error('Please enter a valid email address.');
    }
    if (formData._hp_field) {
      // Silently succeed for bots (don't reveal honeypot)
      return { status: 'ok' };
    }

    // Build payload (without signature yet)
    const payload = {
      source: 'website_form',
      timestamp: new Date().toISOString(),
      form_data: formData,
      metadata: {
        page_url: window.location.href,
        user_agent: navigator.userAgent,
      },
    };

    // Sign and attach HMAC
    if (WEBHOOK_SECRET) {
      payload.hmac_signature = await hmacSign(payload, WEBHOOK_SECRET);
    }

    // Send
    const response = await fetch(WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error('Submission failed (' + response.status + '): ' + text.substring(0, 200));
    }

    return response.json();
  }

  // --- Auto-bind to forms with [data-mahlatini-enquiry] ---
  function bindForms() {
    const forms = document.querySelectorAll('form[data-mahlatini-enquiry]');
    forms.forEach(function (form) {
      if (form._mahlatiniBound) return;
      form._mahlatiniBound = true;

      form.addEventListener('submit', async function (e) {
        e.preventDefault();

        const submitBtn = form.querySelector('[type="submit"]');
        const originalText = submitBtn ? submitBtn.textContent : '';

        try {
          // Disable button and show loading
          if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Sending...';
          }

          const result = await submitEnquiry(form);

          // Success feedback
          if (submitBtn) {
            submitBtn.textContent = 'Sent!';
            submitBtn.classList.add('mahlatini-success');
          }

          // Dispatch custom event for the host page to handle
          form.dispatchEvent(new CustomEvent('mahlatini:enquiry:success', {
            detail: result,
            bubbles: true,
          }));

          // Optional: show a default success message
          const successEl = form.querySelector('[data-mahlatini-success]');
          if (successEl) {
            successEl.style.display = 'block';
          }

          // Reset after 3 seconds
          setTimeout(function () {
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.textContent = originalText;
              submitBtn.classList.remove('mahlatini-success');
            }
            form.reset();
            if (successEl) successEl.style.display = 'none';
          }, 3000);

        } catch (err) {
          // Error feedback
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
          }

          form.dispatchEvent(new CustomEvent('mahlatini:enquiry:error', {
            detail: { error: err.message },
            bubbles: true,
          }));

          // Optional: show a default error message
          const errorEl = form.querySelector('[data-mahlatini-error]');
          if (errorEl) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
            setTimeout(function () { errorEl.style.display = 'none'; }, 5000);
          }
        }
      });
    });
  }

  // --- Initialise ---
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindForms);
  } else {
    bindForms();
  }

  // Expose for programmatic use
  window.MahlatiniEnquiry = {
    submit: submitEnquiry,
    bindForms: bindForms,
  };

})();
