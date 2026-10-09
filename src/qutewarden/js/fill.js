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

function isSelect(el) {
  const view = viewOf(el);
  return Boolean(view) && el instanceof view.HTMLSelectElement;
}

// Set `property` through the prototype's setter so framework value trackers
// (React) notice the change, then fire bubbling input + change events.
function setNative(el, property, value) {
  const view = viewOf(el);
  const proto = isSelect(el) ? view.HTMLSelectElement.prototype : view.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, property).set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function setValue(el, value) {
  setNative(el, "value", value);
}

// The focused input, if it is one we could fill (a focused search box or
// checkbox counts as no focus).
function focusedInput(doc) {
  const el = doc.activeElement;
  if (!isUsable(el)) return null;
  return inputType(el) === "password" || isTextish(el) || looksLikeOtp(el) ? el : null;
}

function loginFields(root) {
  return usableInputs(root).filter((el) => inputType(el) === "password" || isTextish(el));
}

// Where to look for fields: the focused input's <form>, or (no form) its
// nearest ancestor that holds another field (`fields(root)` lists them);
// else the document.
function scopeFor(doc, focused, fields = loginFields) {
  if (!focused) return doc;
  if (focused.form) return focused.form;
  for (let el = focused.parentElement; el; el = el.parentElement) {
    if (fields(el).some((field) => field !== focused)) return el;
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

// --- Fields by kind (Card and Identity items) --------------------------------
//
// A kind is the autocomplete token that names a field ("cc-number"). A field
// whose autocomplete names a kind is that kind; a field with no autocomplete
// token is matched by its name, id, label and placeholder against an ordered
// list of [pattern, kind], the first match deciding. Each kind gives the value
// for a field (`value(el, v)`, null = leave the field alone) and, if plain
// equality isn't enough, which <select> option fits (`option(text, v)` on the
// option's normalised value or text).

const CONTROL_TYPES = ["text", "email", "tel", "number", "password", "search", ""];

// Autocomplete tokens that qualify a kind rather than name one.
const NOT_A_KIND = /^(on|off|section-.*|shipping|billing|home|work|mobile|fax|pager)?$/;

function isFillableControl(el) {
  if (isSelect(el)) {
    return !el.disabled && el.getClientRects().length > 0
      && viewOf(el).getComputedStyle(el).visibility !== "hidden";
  }
  return isUsable(el) && CONTROL_TYPES.includes(inputType(el));
}

function fillableControls(root) {
  return Array.from(root.querySelectorAll("input, select")).filter(isFillableControl);
}

// The focused input or select, if it is one a kind could fill.
function focusedControl(doc) {
  const el = doc.activeElement;
  return el && isFillableControl(el) ? el : null;
}

// The text of the field's labels, without that of controls inside them
// (a <select> in its <label> would add every option).
function labelTexts(el) {
  return Array.from(el.labels || []).map((label) => {
    const copy = label.cloneNode(true);
    for (const inner of copy.querySelectorAll("input, select, textarea, button")) inner.remove();
    return copy.textContent;
  });
}

function labelText(el) {
  return labelTexts(el).join(" ");
}

function describeField(el) {
  return [el.name, el.id, labelText(el), el.getAttribute("placeholder") || ""].join(" ");
}

function normalise(text) {
  return String(text == null ? "" : text).toLowerCase().replace(/[^a-z0-9]/g, "");
}

function kindOf(el, kinds, words) {
  const tokens = autocompleteTokens(el).filter((t) => !NOT_A_KIND.test(t));
  if (tokens.length) return tokens.find((t) => kinds.has(t)) || null;
  const text = describeField(el);
  const hit = words.find(([pattern]) => pattern.test(text));
  return hit ? hit[1] : null;
}

function selectOption(el, kind, v) {
  let fits = kind.option && ((text) => kind.option(text, v));
  if (!fits) {
    const wanted = normalise(kind.value(el, v));
    fits = (text) => wanted !== "" && text === wanted;
  }
  const option = Array.from(el.options).find(
    (o) => !o.disabled && (fits(normalise(o.value)) || fits(normalise(o.text))));
  if (!option) return false;
  setValue(el, option.value);
  return true;
}

// Fill every field in root that has a kind in `kinds` (a Map) and a value in
// `v`; return the fields filled.
function fillKinds(root, kinds, words, v) {
  const filled = [];
  for (const el of fillableControls(root)) {
    const name = kindOf(el, kinds, words);
    if (!name) continue;
    const kind = kinds.get(name);
    if (isSelect(el)) {
      if (selectOption(el, kind, v)) filled.push(el);
      continue;
    }
    const value = kind.value(el, v);
    if (value == null) continue;
    setValue(el, value);
    filled.push(el);
  }
  return filled;
}

// --- Card items ----------------------------------------------------------------
//
// `v` is `a.card`: name, givenName, familyName, number, brand, code, and the
// expiry as expMonth ("03") and expYear ("2030"). Missing values are null.

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

const BRAND_NAMES = {
  amex: ["americanexpress"],
  dinersclub: ["diners"],
  mastercard: ["mc"],
  unionpay: ["chinaunionpay"],
};

// A single expiry field asks for a 4-digit year through its placeholder,
// else its pattern, else a maxlength of at least 7 ("MM/YYYY").
function wantsLongYear(el) {
  const placeholder = el.getAttribute("placeholder") || "";
  if (/yyyy|\d{4}/i.test(placeholder)) return true;
  if (/yy|\d\d/i.test(placeholder)) return false;
  const pattern = el.getAttribute("pattern") || "";
  if (pattern) return /\{4\}|yyyy|\\d\\d\\d\\d/i.test(pattern);
  return el.maxLength >= 7;
}

function wantsShortYear(el) {
  return el.maxLength === 2 || /^\s*yy\s*$/i.test(el.getAttribute("placeholder") || "");
}

function shortYear(year) {
  return year.slice(-2);
}

const CARD_KINDS = new Map([
  ["cc-name", { value: (el, v) => v.name }],
  ["cc-given-name", { value: (el, v) => v.givenName }],
  ["cc-family-name", { value: (el, v) => v.familyName }],
  ["cc-number", { value: (el, v) => v.number }],
  ["cc-csc", { value: (el, v) => v.code }],
  ["cc-type", {
    value: (el, v) => v.brand,
    option: (text, v) => {
      if (v.brand == null || text === "") return false;
      const brand = normalise(v.brand);
      return text === brand || (BRAND_NAMES[brand] || []).includes(text);
    },
  }],
  ["cc-exp", {
    value: (el, v) => (v.expMonth == null || v.expYear == null ? null
      : `${v.expMonth}/${wantsLongYear(el) ? v.expYear : shortYear(v.expYear)}`),
  }],
  ["cc-exp-month", {
    value: (el, v) => v.expMonth,
    option: (text, v) => v.expMonth != null && (
      (/^\d/.test(text) && parseInt(text, 10) === Number(v.expMonth))
      || text.startsWith(MONTHS[Number(v.expMonth) - 1])),
  }],
  ["cc-exp-year", {
    value: (el, v) => (v.expYear == null ? null
      : wantsShortYear(el) ? shortYear(v.expYear) : v.expYear),
    option: (text, v) => v.expYear != null && (text === v.expYear || text === shortYear(v.expYear)),
  }],
]);

// Without autocomplete: the security code first ("card code"), then an
// explicit "MM/YY" (one field), then the split expiry fields. Names are
// never guessed from "first name"/"last name": those are usually shipping.
const CARD_WORDS = [
  [/cvv|cvc|csc|cvn|security.?code|card.?code|card.?verification/i, "cc-csc"],
  [/mm\s*\/\s*yy/i, "cc-exp"],
  [/month|\bmm\b/i, "cc-exp-month"],
  [/year|\byy(yy)?\b/i, "cc-exp-year"],
  [/exp|valid.?(thru|through|until)/i, "cc-exp"],
  [/card.?(num|no\b)|cc.?num|\bpan\b/i, "cc-number"],
  [/card.?holder|name.?on.?card|cc.?name|holder/i, "cc-name"],
  [/card.?(type|brand)|cc.?type/i, "cc-type"],
];

// --- Identity items --------------------------------------------------------------
//
// `v` is `a.identity`: one value per kind below (streetAddress is every
// address line joined). Missing values are null. A <select> (country, say)
// takes the option whose value or text is the value.

const IDENTITY_KINDS = new Map([
  ["honorific-prefix", { value: (el, v) => v.honorificPrefix }],
  ["given-name", { value: (el, v) => v.givenName }],
  ["additional-name", { value: (el, v) => v.additionalName }],
  ["family-name", { value: (el, v) => v.familyName }],
  ["organization", { value: (el, v) => v.organization }],
  ["street-address", { value: (el, v) => v.streetAddress }],
  ["address-line1", { value: (el, v) => v.addressLine1 }],
  ["address-line2", { value: (el, v) => v.addressLine2 }],
  ["address-line3", { value: (el, v) => v.addressLine3 }],
  ["address-level1", { value: (el, v) => v.addressLevel1 }],
  ["address-level2", { value: (el, v) => v.addressLevel2 }],
  ["postal-code", { value: (el, v) => v.postalCode }],
  ["country", { value: (el, v) => v.country }],
  ["country-name", { value: (el, v) => v.country }],
  ["email", { value: (el, v) => v.email }],
  ["tel", { value: (el, v) => v.tel }],
  ["username", { value: (el, v) => v.username }],
]);

// Without autocomplete. Order matters: "Email address" is an email field and
// "Address line 2" isn't line 1; a bare "Name" is never guessed.
const IDENTITY_WORDS = [
  [/e-?mail/i, "email"],
  [/phone|\btel\b|mobile/i, "tel"],
  [/user.?name|login/i, "username"],
  [/zip|postal|post.?code/i, "postal-code"],
  [/country/i, "country"],
  [/state|province|region|county/i, "address-level1"],
  [/city|town|locality/i, "address-level2"],
  [/address.?(line)?.?2|addr.?2|\bapt\b|suite|apartment/i, "address-line2"],
  [/address.?(line)?.?3|addr.?3/i, "address-line3"],
  [/address|street|addr/i, "address-line1"],
  [/middle/i, "additional-name"],
  [/first|given|fname|forename/i, "given-name"],
  [/last.?name|surname|family|lname/i, "family-name"],
  [/company|organi[sz]ation|\borg\b|business/i, "organization"],
  [/\btitle\b|salutation|honorific/i, "honorific-prefix"],
];

// Fill an Item that isn't a Login (a.mode "card" or "identity") into root,
// the focused field's scope; return the fields filled. Never submits.
function fillItem(root, a) {
  switch (a.mode) {
    case "card": return fillKinds(root, CARD_KINDS, CARD_WORDS, a.card);
    case "identity": return fillKinds(root, IDENTITY_KINDS, IDENTITY_WORDS, a.identity);
  }
  return [];
}

// --- Custom fields ----------------------------------------------------------------
//
// `a.fields` is the Item's Custom fields that have a value: {name, kind, value},
// kind "text", "hidden", "boolean" or "linked" (whose value Python already
// resolved to the built-in value it stands for). A field fills the first input
// whose name, id, label, aria-label or placeholder equals its name, ignoring
// case and surrounding whitespace; a boolean ("true"/"false") only a checkbox
// or radio button, the others only an input that takes text.

const CHECKABLE_TYPES = ["checkbox", "radio"];
const NOT_TEXT_TYPES = [...CHECKABLE_TYPES, "file", "submit", "reset", "button", "image",
  "range", "color"];

function namesOf(el) {
  return [el.name, el.id, ...labelTexts(el), el.getAttribute("aria-label"),
    el.getAttribute("placeholder")].map((text) => (text || "").trim().toLowerCase());
}

function setChecked(el, on) {
  setNative(el, "checked", on);
}

// Fill `fields` into root (the built-in fill's scope), leaving alone the
// fields in `filled` (what the built-in fill filled: a Custom field never
// overrides it). Returns the inputs filled.
function fillCustomFields(root, fields, filled) {
  const taken = new Set(filled);
  const done = [];
  const inputs = usableInputs(root);
  for (const field of fields || []) {
    const wanted = field.name.trim().toLowerCase();
    const boolean = field.kind === "boolean";
    const el = wanted && inputs.find((input) => !taken.has(input)
      && (boolean ? CHECKABLE_TYPES.includes(inputType(input))
        : !NOT_TEXT_TYPES.includes(inputType(input)))
      && namesOf(input).includes(wanted));
    if (!el) continue;
    if (boolean) {
      setChecked(el, field.value.trim().toLowerCase() === "true");
    } else {
      setValue(el, field.value);
    }
    taken.add(el);
    done.push(el);
  }
  return done;
}

// Run the built-in fill (`fillOne(root, focused)`, returning the fields it
// filled) on the targets until one fills something, then the Custom fields in
// that same scope: `scopeOf(target)`, the focused input's form, else its
// nearest ancestor holding another field, else the document. If the built-in
// fill finds nothing anywhere, the Custom fields fill the first target's scope
// where they match. Returns the built-in fields filled.
function fillWithCustomFields(targets, fields, scopeOf, fillOne) {
  for (const target of targets) {
    const root = scopeOf(target);
    const filled = fillOne(root, target.focused);
    if (filled.length) {
      fillCustomFields(root, fields, filled);
      return filled;
    }
  }
  for (const target of targets) {
    if (fillCustomFields(scopeOf(target), fields, []).length) break;
  }
  return [];
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
// `focusOf(doc)` is the mode's idea of a focused field (focusedControl for
// Card and Identity items, which also counts a <select>).
function fillTargets(top, origin, focusOf = focusedInput) {
  const focusedDoc = focusedDocument(top);
  const focused = focusOf(focusedDoc);
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
  if (a.mode === "card" || a.mode === "identity") {
    // Never submits, whatever `a.submit` says: an unwanted card submit can be
    // a purchase, and an identity fill is usually one step of a longer form
    // (ADR-0005).
    fillWithCustomFields(fillTargets(document, a.origin, focusedControl), a.fields,
      ({ doc, focused }) => scopeFor(doc, focused, fillableControls),
      (root) => fillItem(root, a));
    return;
  }
  const targets = fillTargets(document, a.origin);
  if (!targets.length) return;
  if (a.mode === "probe") {
    probeUsername(targets, a.probeNonce);
    return;
  }
  if (a.probeNonce && location.origin === a.origin) {
    document.documentElement.removeAttribute(probeAttribute(a.probeNonce));
  }
  const filled = fillWithCustomFields(targets, a.fields,
    ({ doc, focused }) => scopeFor(doc, focused),
    (root, focused) => fillDocument(root, a, focused));
  if (filled.length && a.submit) submitAfter(filled);
}
