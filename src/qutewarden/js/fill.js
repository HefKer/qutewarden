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
  const texts = usableInputs(root).filter(isTextish);
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

function qutewardenFill(a) {
  if (location.origin !== a.origin) return;
  fillLogin(document, a);
}
