### Pay button is a div
Severity: high. The Pay now control is a `div` with `onclick`: keyboard and screen-reader users can't reach or use it, so they can't pay. Fix: use `<button type="submit" class="pay">Pay now</button>`.

### Card input has no label
Severity: high. The card field only has a placeholder, which disappears on typing and isn't read reliably. Fix: add `<label for="card">Card number</label>` and `id="card"`, plus `autocomplete="cc-number"`.

### Error is only red and says "Invalid"
Severity: medium. Colour alone carries the error and the text doesn't say what's wrong. Fix: "Enter a 16-digit card number", tied to the input with `aria-describedby`, and an icon or prefix that isn't colour.

### Hint text has low contrast
Severity: medium. #b0b0b0 on white is about 2.1:1, below 4.5:1. Fix: use #595959 or darker.

### Logo image has no alt text
Severity: low. Screen readers announce the file name. Fix: `alt="Acme"` (or `alt=""` if decorative).
