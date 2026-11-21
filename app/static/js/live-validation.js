// Live validation hints for the expense form. The rules and messages come from the server
// (data-live-validation), so a hint says exactly what the server would. The server still checks everything.
// A field is checked once the user leaves it (or picks a value), then again as they type.
(function () {
  "use strict";

  var form = document.querySelector("form[data-live-validation]");
  if (!form) return;
  var rules;
  try { rules = JSON.parse(form.dataset.liveValidation); }
  catch (error) { return; } // no hints; the server messages still apply

  var checks = {
    amount: function (input, r) {
      var text = input.value.trim();
      if (!text) return r.required;
      if (text.charAt(0) === "-") return r.positive;
      var match = /^(\d*)(?:\.(\d+))?$/.exec(text);
      if (!match || (match[1] === "" && match[2] === undefined)) return r.format;
      var whole = match[1].replace(/^0+/, "");
      var fraction = match[2] || "";
      if (!whole && /^0*$/.test(fraction)) return r.positive;
      if (whole.length > 6) return r.limit;
      if (fraction.length > 2) return r.places;
      return "";
    },
    category: function (input, r) { return input.value ? "" : r.required; },
    spent_on: function (input, r) {
      if (input.validity && input.validity.badInput) return r.invalid;
      var value = input.value;
      if (!value) return r.required;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return r.invalid;
      if (value < r.min) return r.too_early; // ISO dates compare correctly as strings
      if (value > r.max) return r.future;
      return "";
    },
    note: function (input, r) {
      return input.value.trim().length > r.max_length ? r.too_long : "";
    },
  };

  function describedBy(input, id, add) {
    var ids = (input.getAttribute("aria-describedby") || "").split(/\s+/).filter(function (part) {
      return part && part !== id;
    });
    if (add) ids.push(id);
    if (ids.length) input.setAttribute("aria-describedby", ids.join(" "));
    else input.removeAttribute("aria-describedby");
  }

  // Same markup as the server's field macro: <p class="field-error" id="<id>-error"> just above the input.
  function show(input, message) {
    var wrapper = input.closest(".field");
    var errorId = input.id + "-error";
    var error = document.getElementById(errorId);
    if (message) {
      if (!error) {
        error = document.createElement("p");
        error.className = "field-error";
        error.id = errorId;
        input.parentNode.insertBefore(error, input);
      }
      error.textContent = message;
      input.setAttribute("aria-invalid", "true");
      describedBy(input, errorId, true);
      if (wrapper) wrapper.classList.add("field-invalid");
    } else {
      if (error) error.remove();
      input.removeAttribute("aria-invalid");
      describedBy(input, errorId, false);
      if (wrapper) wrapper.classList.remove("field-invalid");
    }
  }

  function check(input) {
    var message = checks[input.name](input, rules[input.name]);
    show(input, message);
    return message;
  }

  var inputs = Object.keys(checks)
    .map(function (name) {
      return form.elements.namedItem(name);
    })
    .filter(function (input) {
      return input && rules[input.name];
    });

  inputs.forEach(function (input) {
    // A field the server already marked wrong is checked live from the start, so its hint clears once fixed.
    var touched = input.getAttribute("aria-invalid") === "true";
    input.addEventListener("blur", function () {
      touched = true;
      check(input);
    });
    input.addEventListener("change", function () {
      touched = true; // picking a category or a date is a finished choice
      check(input);
    });
    input.addEventListener("input", function () {
      if (touched) check(input);
    });
  });

  // The hints replace the browser's own bubbles; the server is still the final check.
  form.noValidate = true;
  form.addEventListener("submit", function (event) {
    var firstInvalid = null;
    inputs.forEach(function (input) {
      if (check(input) && !firstInvalid) firstInvalid = input;
    });
    if (firstInvalid) {
      event.preventDefault();
      firstInvalid.focus();
    }
  });
})();
