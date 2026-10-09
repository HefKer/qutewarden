// qutewarden fill script. Rendered by qutewarden/filljs.py, which appends
// one call `qutewardenFill(<json args>);` and wraps both in an IIFE.
// Runs in an isolated JS world: the page's scripts can't see these
// functions or the values in `a`, but the DOM is shared.
"use strict";

const TEXT_TYPES = ["text", "email", "tel", ""];

function inputType(el) {
  return (el.getAttribute("type") || "").toLowerCase();
}

// The element's own window: a frame's elements belong to the frame's realm,
// so `instanceof` and prototype setters must come from there.
function viewOf(el) {
  return el && el.ownerDocument ? el.ownerDocument.defaultView : null;
}

function isInput(el) {
  const view = viewOf(el);
  return Boolean(view) && el instanceof view.HTMLInputElement;
}

function isUsable(el) {
  if (!isInput(el) || el.disabled || el.readOnly) return false;
  if (inputType(el) === "hidden") return false;
  if (el.getClientRects().length === 0) return false;
  const style = viewOf(el).getComputedStyle(el);
  return style.visibility !== "hidden" && style.display !== "none";
}

function isTextish(el) {
  return TEXT_TYPES.includes(inputType(el));
}

function autocompleteTokens(el) {
  return (el.getAttribute("autocomplete") || "").toLowerCase().split(/\s+/);
}

function hasAutocomplete(el, token) {
  return autocompleteTokens(el).includes(token);
}

function usableInputs(root) {
  return Array.from(root.querySelectorAll("input")).filter(isUsable);
}

function passwordFields(root) {
  return usableInputs(root).filter((el) => inputType(el) === "password");
}

function precedes(a, b) {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}

function looksLikeUsername(el) {
  if (hasAutocomplete(el, "username") || hasAutocomplete(el, "email")) return true;
  if (inputType(el) === "email") return true;
  const words = `${el.name} ${el.id}`;
  return /user|login|email|e-mail|account|ident/i.test(words);
}

// Username field: autocomplete=username/email first, then the nearest
// text-ish input before the password field, then a username-looking input.
function findUsernameField(root, passwordField) {
  const texts = usableInputs(root).filter((el) => isTextish(el) && !looksLikeOtp(el));
  const byAutocomplete = texts.find(
    (el) => hasAutocomplete(el, "username") || hasAutocomplete(el, "email"));
  if (byAutocomplete) return byAutocomplete;
  if (passwordField) {
    const before = texts.filter((el) => precedes(el, passwordField));
    if (before.length) return before[before.length - 1];
  }
  return texts.find(looksLikeUsername) || null;
}

function findLoginPasswordField(root) {
  const fields = passwordFields(root);
  return fields.find((el) => hasAutocomplete(el, "current-password"))
    || fields.find((el) => !hasAutocomplete(el, "new-password"))
    || fields[0] || null;
}

// Set through the prototype's setter so framework value trackers (React)
// notice the change, then fire bubbling input + change events.
function setValue(el, value) {
  const proto = viewOf(el).HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

// The focused input, if it is one we could fill (a focused search box or
// checkbox counts as no focus).
function focusedInput(doc) {
  const el = doc.activeElement;
  if (!isUsable(el)) return null;
  return inputType(el) === "password" || isTextish(el) || looksLikeOtp(el) ? el : null;
}

// Where to look for fields: the focused input's <form>, or (no form) its
// nearest ancestor that holds another fillable field; else the document.
function scopeFor(doc, focused) {
  if (!focused) return doc;
  if (focused.form) return focused.form;
  const isField = (el) => el !== focused && (inputType(el) === "password" || isTextish(el));
  for (let el = focused.parentElement; el; el = el.parentElement) {
    if (usableInputs(el).some(isField)) return el;
  }
  return doc;
}

function fillLogin(root, a, focused) {
  let passwordField = null;
  let usernameField = null;
  if (focused && inputType(focused) === "password") {
    passwordField = focused;
  } else if (focused && isTextish(focused) && !looksLikeOtp(focused)) {
    usernameField = focused;
  }
  passwordField = passwordField || findLoginPasswordField(root);
  usernameField = usernameField || findUsernameField(
    passwordField ? (passwordField.form || root) : root, passwordField);
  const filled = [];
  if (usernameField && a.username != null) {
    setValue(usernameField, a.username);
    filled.push(usernameField);
  }
  if (passwordField && a.password != null) {
    setValue(passwordField, a.password);
    filled.push(passwordField);
  }
  return filled;
}

const OTP_NAME = /otp|totp|2fa|mfa|one.?time|verification|code|token/i;

function looksLikeOtp(el) {
  if (hasAutocomplete(el, "one-time-code")) return true;
  if (!(isTextish(el) || inputType(el) === "number")) return false;
  if (!OTP_NAME.test(`${el.name} ${el.id}`)) return false;
  const max = el.maxLength;
  return (max >= 4 && max <= 8) || (el.getAttribute("inputmode") || "") === "numeric";
}

function findOtpField(root) {
  const inputs = usableInputs(root);
  return inputs.find((el) => hasAutocomplete(el, "one-time-code"))
    || inputs.find(looksLikeOtp) || null;
}

function fillOtp(root, a, focused) {
  if (a.totp == null) return [];
  const field = (focused && isTextish(focused) && focused) || findOtpField(root);
  if (!field) return [];
  setValue(field, a.totp);
  return [field];
}

// Every new-password field (password + confirmation), or every password
// field if the page marks none.
function newPasswordFields(root) {
  const passwords = passwordFields(root);
  const marked = passwords.filter((el) => hasAutocomplete(el, "new-password"));
  return marked.length ? marked : passwords;
}

// The username field on a signup page: the focused text input if it looks
// like a username field (#24), else the username field relative to the
// first new-password field.
function findSignupUsernameField(root, focused) {
  return (focused && isTextish(focused) && looksLikeUsername(focused) && focused)
    || findUsernameField(root, newPasswordFields(root)[0] || null);
}

// The new-password fields (spec, `generate` step 3), plus the username field
// if `a.username` is given and that field is still empty (#16). Without a
// new-password field nothing is filled, so nothing is submitted either.
function fillNewPassword(root, a, focused) {
  const targets = newPasswordFields(root);
  if (a.password == null || !targets.length) return [];
  const filled = [];
  if (a.username != null) {
    const field = findSignupUsernameField(root, focused);
    if (field && field.value === "") {
      setValue(field, a.username);
      filled.push(field);
    }
  }
  for (const el of targets) setValue(el, a.password);
  return [...filled, ...targets];
}

// Page-kind decision for `auto` (Python can't get a reply from the page):
// a password field means a login page; else an OTP field means an OTP page;
// else fill whatever login fields there are (two-step page 1).
function fillAuto(root, a, focused) {
  if (passwordFields(root).length) return fillLogin(root, a, focused);
  if (findOtpField(root)) return fillOtp(root, a, focused);
  return fillLogin(root, a, focused);
}

// Submit controls for pages without a <form>, best first. Each selector is
// tried across every ancestor before the next one, so a real submit button
// further out beats a generic button next to the field.
const SUBMIT_SELECTORS = [
  "button[type=submit], input[type=submit], input[type=image]",
  "button:not([type])",
  "button[type=button], [role=button]",
];
const EXPLICIT_SUBMIT = SUBMIT_SELECTORS[0];

const TOGGLE_WORDS = /show|hide|reveal|toggle|visib|eye|peek/i;

function looksLikeToggle(el) {
  if (el.hasAttribute("aria-pressed")) return true;
  const words = ["aria-label", "title", "id", "class", "name"]
    .map((attr) => el.getAttribute(attr) || "").join(" ");
  return TOGGLE_WORDS.test(`${words} ${el.textContent || ""}`);
}

// A generic button is unsafe to click if it sits in a filled field's own
// wrapper (show-password toggles, clear buttons) or looks like a toggle.
function isSafeButton(button, filled) {
  if (button.disabled || button.getClientRects().length === 0) return false;
  if (button.matches(EXPLICIT_SUBMIT)) return true;
  if (filled.some((field) => field.parentElement && field.parentElement.contains(button))) {
    return false;
  }
  return !looksLikeToggle(button);
}

// Nearest safe submit control around the filled fields (no <form>), or null.
function findSubmitButton(filled) {
  const start = filled[filled.length - 1];
  for (const selector of SUBMIT_SELECTORS) {
    for (let node = start.parentElement; node; node = node.parentElement) {
      const button = Array.from(node.querySelectorAll(selector))
        .find((b) => isSafeButton(b, filled));
      if (button) return button;
    }
  }
  return null;
}

// The form's default button: its first submit button in tree order,
// including ones outside it linked with form=. form.elements would miss
// input[type=image], so walk the form's tree instead. Unlike EXPLICIT_SUBMIT,
// el.type also counts a <button> with no or an invalid type. Null if disabled
// (also by a disabled <fieldset>), so the form is submitted without a submitter.
function defaultButton(form) {
  const button = Array.from(form.getRootNode().querySelectorAll("button, input"))
    .find((el) => el.form === form && (el.type === "submit" || el.type === "image"));
  return button && !button.matches(":disabled") ? button : null;
}

function submitAfter(filled) {
  const field = filled[filled.length - 1];
  if (field.form) {
    // With a submitter, its name/value is sent, like pressing Enter would.
    field.form.requestSubmit(defaultButton(field.form));
    return;
  }
  const button = findSubmitButton(filled);
  if (button) button.click();
}

// Frames (spec-v2 "Iframes"): only same-origin frames are reachable. A
// cross-origin frame's contentDocument is null or throws a SecurityError,
// so it is skipped together with everything inside it.
function frameDocument(el) {
  if (!el || !["iframe", "frame"].includes(el.localName)) return null;
  try {
    return el.contentDocument;
  } catch (e) {
    if (e && e.name === "SecurityError") return null;
    throw e;
  }
}

// The top document, then every reachable frame's document in tree order.
function reachableDocuments(doc) {
  const docs = [doc];
  for (const el of doc.querySelectorAll("iframe, frame")) {
    const inner = frameDocument(el);
    if (inner) docs.push(...reachableDocuments(inner));
  }
  return docs;
}

// The innermost reachable document that has focus.
function focusedDocument(doc) {
  for (let inner = frameDocument(doc.activeElement); inner;
    inner = frameDocument(doc.activeElement)) {
    doc = inner;
  }
  return doc;
}

// The documents to try, best first, each with its focused input: the
// focused document if it has a fillable focused input, then the rest in
// tree order. Only documents whose own origin is the expected one.
function fillTargets(top, origin) {
  const focusedDoc = focusedDocument(top);
  const focused = focusedInput(focusedDoc);
  const docs = reachableDocuments(top);
  const ordered = focused ? [focusedDoc, ...docs.filter((d) => d !== focusedDoc)] : docs;
  return ordered
    .filter((doc) => doc.location && doc.location.origin === origin)
    .map((doc) => ({ doc, focused: doc === focusedDoc ? focused : null }));
}

function probeAttribute(nonce) {
  return `data-qutewarden-probe-${nonce}`;
}

// Secret-free: copy the username the user typed on a signup page into an
// attribute that qutebrowser's DOM dump (QUTE_HTML) carries back to Python.
// The attribute goes on the top document, the one QUTE_HTML dumps.
function probeUsername(targets, nonce) {
  let value = "";
  for (const { doc, focused } of targets) {
    const field = findSignupUsernameField(scopeFor(doc, focused), focused);
    if (field) {
      value = field.value;
      break;
    }
  }
  document.documentElement.setAttribute(probeAttribute(nonce), value);
}

function fillDocument(root, a, focused) {
  switch (a.mode) {
    case "auto": return fillAuto(root, a, focused);
    case "login": return fillLogin(root, a, focused);
    case "otp": return fillOtp(root, a, focused);
    case "new_password": return fillNewPassword(root, a, focused);
  }
  return [];
}

// Fills the first target document in which the mode finds fields.
function qutewardenFill(a) {
  const targets = fillTargets(document, a.origin);
  if (!targets.length) return;
  if (a.mode === "probe") {
    probeUsername(targets, a.probeNonce);
    return;
  }
  if (a.probeNonce && location.origin === a.origin) {
    document.documentElement.removeAttribute(probeAttribute(a.probeNonce));
  }
  for (const { doc, focused } of targets) {
    const filled = fillDocument(scopeFor(doc, focused), a, focused);
    if (filled.length) {
      if (a.submit) submitAfter(filled);
      return;
    }
  }
}
