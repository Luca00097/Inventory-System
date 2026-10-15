/*
 * Auto-fills the unit price field when a product is picked in a
 * Sale Item (or Purchase Item) inline row. The price is still a
 * normal editable field afterward — this just saves retyping a
 * number that's already on the Product record.
 *
 * Works for rows already on the page AND rows added later via
 * Django admin's "Add another" button, since it listens on the
 * document rather than on the rows themselves.
 */
(function () {
  function getPriceMap() {
    var el = document.getElementById("product-price-map");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent);
    } catch (e) {
      return {};
    }
  }

  function findSiblingInput(productSelect, suffix) {
    // product select name looks like "items-0-product" or "0-product";
    // the price field is the same prefix with a different suffix.
    var name = productSelect.getAttribute("name");
    if (!name) return null;
    var targetName = name.replace(/-product$/, suffix);
    var row = productSelect.closest("tr") || productSelect.closest(".form-row") || document;
    return row.querySelector('[name="' + targetName + '"]');
  }

  function applyPrice(productSelect) {
    var priceField = findSiblingInput(productSelect, "-unit_price");
    if (!priceField) priceField = findSiblingInput(productSelect, "-unit_cost");
    if (!priceField) return;

    // Don't clobber a price the user already typed in manually for this row.
    if (priceField.dataset.autofilled !== "true" && priceField.value) return;

    var priceMap = getPriceMap();
    var productId = productSelect.value;
    if (productId && priceMap[productId] !== undefined) {
      priceField.value = priceMap[productId];
      priceField.dataset.autofilled = "true";
    }
  }

  document.addEventListener("change", function (e) {
    var target = e.target;
    if (target.tagName === "SELECT" && target.name && target.name.match(/-product$/)) {
      applyPrice(target);
    }
  });
})();
