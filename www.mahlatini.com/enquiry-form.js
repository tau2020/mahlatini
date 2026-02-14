/**
 * Mahlatini Enquiry Form Submission Handler
 * ==========================================
 * Embeddable script that captures website enquiry forms and sends
 * them to the n8n webhook for processing → Outlook + Gemini classification.
 *
 * Usage:
 *   <script src="/enquiry-form.js"
 *           data-webhook-url="http://localhost:5678/webhook/website-enquiry"
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

  const scriptTag = document.currentScript;
  const WEBHOOK_URL = scriptTag?.getAttribute('data-webhook-url') || '/webhook/website-enquiry';

  function extractFormData(form) {
    const fd = new FormData(form);
    const raw = {};
    for (const [key, value] of fd.entries()) {
      raw[key] = value;
    }

    return {
      name: raw.name || raw.full_name || '',
      email: raw.email || raw.email_address || '',
      phone: raw.phone || raw.telephone || '',
      destination: raw.destination || raw.country || '',
      travel_dates: raw.travel_dates || raw.dates || '',
      duration: raw.duration || '',
      party_size: {
        adults: parseInt(raw.adults || '0') || 0,
        children: parseInt(raw.children || '0') || 0,
        children_ages: raw.children_ages
          ? raw.children_ages.split(',').map(a => parseInt(a.trim())).filter(Boolean)
          : [],
      },
      budget_range: raw.budget || '',
      experience_type: raw.experience_type
        ? raw.experience_type.split(',').map(s => s.trim())
        : [],
      special_occasion: raw.special_occasion || null,
      message: raw.message || raw.comments || '',
      how_heard: raw.how_heard || '',
      newsletter_consent: raw.newsletter === 'on',
      _hp_field: raw._hp_field || '',
    };
  }

  async function submitEnquiry(form) {
    const formData = extractFormData(form);

    if (!formData.name || formData.name.trim().length < 2) {
      throw new Error('Please enter your name.');
    }
    if (!formData.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      throw new Error('Please enter a valid email address.');
    }
    if (formData._hp_field) {
      return { status: 'ok' };
    }

    const payload = {
      source: 'website_form',
      timestamp: new Date().toISOString(),
      form_data: formData,
      metadata: {
        page_url: window.location.href,
        user_agent: navigator.userAgent,
      },
    };

    const response = await fetch(WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error('Submission failed (' + response.status + '): ' + text.substring(0, 200));
    }

    return response.json().catch(() => ({ status: 'ok' }));
  }

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
          if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Sending...';
          }

          const result = await submitEnquiry(form);

          if (submitBtn) {
            submitBtn.textContent = 'Sent!';
            submitBtn.style.background = '#28a745';
          }

          const successEl = form.querySelector('[data-mahlatini-success]');
          if (successEl) {
            successEl.style.display = 'block';
          }

          setTimeout(function () {
            if (submitBtn) {
              submitBtn.disabled = false;
              submitBtn.textContent = originalText;
              submitBtn.style.background = '';
            }
            form.reset();
            if (successEl) successEl.style.display = 'none';
          }, 4000);

        } catch (err) {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
          }

          const errorEl = form.querySelector('[data-mahlatini-error]');
          if (errorEl) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
            setTimeout(function () { errorEl.style.display = 'none'; }, 5000);
          } else {
            alert('Error: ' + err.message);
          }
        }
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindForms);
  } else {
    bindForms();
  }

  window.MahlatiniEnquiry = { submit: submitEnquiry, bindForms: bindForms };
})();
