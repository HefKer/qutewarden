// qutewarden fill script. Rendered by qutewarden/filljs.py, which appends
// one call `qutewardenFill(<json args>);` and wraps both in an IIFE.
// Runs in an isolated JS world: the page's scripts can't see these
// functions or the values in `a`, but the DOM is shared.
"use strict";

const TEXT_TYPES = ["text", "email", "tel", ""];

function inputType(el) {
  return (el.getAttribute("type") || "").toLowerCase();
}

function isUsable(el) {
  if (!(el instanceof HTMLInputElement) || el.disabled || el.readOnly) return false;
  if (inputType(el) === "hidden") return false;
  if (el.getClientRects().length === 0) return false;
  const style = getComputedStyle(el);
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

const nativeValueSetter =
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;

// Set through the prototype's setter so framework value trackers (React)
// notice the change, then fire bubbling input + change events.
function setValue(el, value) {
  nativeValueSetter.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function fillLogin(root, a) {
  const passwordField = findLoginPasswordField(root);
  const usernameField = findUsernameField(passwordField ? (passwordField.form || root) : root,
    passwordField);
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
// field if the page marks none; plus the username if its field is empty.
function fillNewPassword(root, a) {
  const passwords = passwordFields(root);
  const marked = passwords.filter((el) => hasAutocomplete(el, "new-password"));
  const targets = marked.length ? marked : passwords;
  const filled = [];
  if (a.username != null) {
    const usernameField = findUsernameField(root, targets[0] || null);
    if (usernameField && usernameField.value === "") {
      setValue(usernameField, a.username);
      filled.push(usernameField);
    }
  }
  if (a.password != null) {
    for (const el of targets) {
      setValue(el, a.password);
      filled.push(el);
    }
  }
  return filled;
}

// Page-kind decision for `auto` (Python can't get a reply from the page):
// a password field means a login page; else an OTP field means an OTP page;
// else fill whatever login fields there are (two-step page 1).
function fillAuto(root, a) {
  if (passwordFields(root).length) return fillLogin(root, a);
  if (findOtpField(root)) return fillOtp(root, a, null);
  return fillLogin(root, a);
}

function qutewardenFill(a) {
  if (location.origin !== a.origin) return;
  const root = document;
  switch (a.mode) {
    case "auto": fillAuto(root, a); break;
    case "login": fillLogin(root, a); break;
    case "otp": fillOtp(root, a, null); break;
    case "new_password": fillNewPassword(root, a); break;
  }
}
