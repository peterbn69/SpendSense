// Category filter for the expense list. Without JS the GET form reloads the page filtered by the server;
// with JS, changing the select filters at once by toggling the `hidden` attribute the server also uses.
(function () {
  "use strict";

  var form = document.querySelector("[data-category-filter]");
  if (!form) return;
  var select = form.querySelector("select[name='category']");
  var submit = form.querySelector("[data-category-filter-submit]");
  var items = document.querySelectorAll(".expense-item[data-category]");
  var count = document.querySelector("[data-filter-count]");
  var empty = document.querySelector("[data-filter-empty]");
  if (!select) return;

  function plural(n) { return n === 1 ? "" : "s"; }

  function apply() {
    var category = select.value;
    var shown = 0;
    items.forEach(function (item) {
      var match = !category || item.dataset.category === category;
      item.hidden = !match;
      if (match) shown += 1;
    });

    if (count) {
      var total = items.length;
      count.textContent = category
        ? shown + " of " + total + " expenses, newest first."
        : total + " expense" + plural(total) + ", newest first.";
    }
    if (empty) empty.hidden = shown > 0;

    // Keep the address in step, so reloading or sharing the page shows the same filter.
    var url = new URL(window.location.href);
    if (category) url.searchParams.set("category", category);
    else url.searchParams.delete("category");
    window.history.replaceState(null, "", url);
  }

  if (submit) submit.hidden = true; // filtering happens on change, so the button is only needed without JS
  select.addEventListener("change", apply);
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    apply();
  });
})();
