// Live running total: "Spent in November 2026: $412.50" plus the amount being typed.
// Shared by the expense form and the landing-page demo. Money is added as integer cents, never floats.
(function () {
  "use strict";

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December"];
  var LIMIT_CENTS = 100000000; // amounts must be under 1,000,000.00

  // "12", "12.5", "12.50", ".5" -> cents; anything else -> null
  function amountToCents(text) {
    var match = /^(\d*)(?:\.(\d{1,2}))?$/.exec(text.trim());
    if (!match || (match[1] === "" && match[2] === undefined)) return null;
    var cents = Number(match[1] || "0") * 100 + Number(((match[2] || "") + "00").slice(0, 2));
    return cents > 0 && cents < LIMIT_CENTS ? cents : null;
  }

  // Totals from the server are always "digits.two digits"; anything else counts as zero.
  function totalToCents(text) {
    var match = /^(\d+)\.(\d{2})$/.exec(String(text));
    return match ? Number(match[1]) * 100 + Number(match[2]) : 0;
  }

  function formatCents(cents) {
    var dollars = Math.floor(cents / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return "$" + dollars + "." + String(cents % 100).padStart(2, "0");
  }

  function monthLabel(key) {
    var parts = key.split("-");
    return MONTHS[Number(parts[1]) - 1] + " " + parts[0];
  }

  function setUp(output) {
    var totals;
    try { totals = JSON.parse(output.dataset.monthTotals || "{}"); }
    catch (error) { return; } // keep the server's text
    var amountInput = document.getElementById(output.dataset.amountInput || "");
    var dateInput = document.getElementById(output.dataset.dateInput || "");
    var defaultMonth = output.dataset.month;
    var monthSlot = output.querySelector("[data-running-total-month]");
    var valueSlot = output.querySelector("[data-running-total-value]");
    if (!amountInput || !monthSlot || !valueSlot || !/^\d{4}-\d{2}$/.test(defaultMonth || "")) return;

    function currentMonth() {
      // A date input's value is "" until it holds a complete, real date.
      var match = dateInput ? /^(\d{4}-\d{2})-\d{2}$/.exec(dateInput.value) : null;
      return match ? match[1] : defaultMonth;
    }

    function update() {
      var month = currentMonth();
      var cents = totalToCents(totals[month] || "0.00") + (amountToCents(amountInput.value) || 0);
      monthSlot.textContent = monthLabel(month);
      valueSlot.textContent = formatCents(cents);
    }

    amountInput.addEventListener("input", update);
    if (dateInput) {
      dateInput.addEventListener("input", update);
      dateInput.addEventListener("change", update);
    }
    update();
  }

  document.querySelectorAll("[data-running-total-reveal]").forEach(function (element) {
    element.hidden = false;
  });
  document.querySelectorAll("[data-running-total]").forEach(setUp);
})();
