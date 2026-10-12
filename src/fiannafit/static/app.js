// Keep the exercise just logged to in view, above the pinned log panel (DAI-11).
// On a phone the page scrolls behind the panel, so tell the browser how much of
// the bottom of the screen the panel covers, then scroll only if needed.
function showCurrentExercise() {
  const panel = document.getElementById("log-panel");
  if (panel) {
    document.documentElement.style.scrollPaddingBottom = panel.offsetHeight + "px";
  }
  document.getElementById("current-exercise")?.scrollIntoView({ block: "nearest" });
}

document.addEventListener("DOMContentLoaded", showCurrentExercise);
// Only after logging a set. Tapping a card, typing a name or Undo also swap in
// parts of the screen, and scrolling then would jump away from what was tapped.
document.addEventListener("htmx:afterSettle", (event) => {
  if (event.detail.requestConfig?.path === "/sets") {
    showCurrentExercise();
  }
});

// The browser's own suggestion dropdown (the Exercise field's <datalist>)
// redraws on every keystroke, which is noisy while typing or clearing the
// field. Unlink it while typing and link it again once typing pauses.
// A stopgap until DAI-14 replaces the datalist with our own list.
const SUGGESTIONS_SETTLE_MS = 400;
let suggestionsTimer;
document.addEventListener("input", (event) => {
  const field = event.target;
  if (field.name !== "exercise") return;
  field.removeAttribute("list");
  clearTimeout(suggestionsTimer);
  suggestionsTimer = setTimeout(
    () => field.setAttribute("list", "exercise-suggestions"),
    SUGGESTIONS_SETTLE_MS,
  );
});

// Clear Exercise empties the name, reps and kg in one tap, ready for the next
// exercise (DAI-29). Typing a logged name re-fills reps and kg as usual.
// Pressing it mustn't take focus from the name field, or the phone's keyboard
// drops and pops back up. The input event lets HTMX and the suggestions code
// see the change.
document.addEventListener("mousedown", (event) => {
  if (event.target.closest("[data-clear-exercise]")) event.preventDefault();
});

document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-clear-exercise]")) return;
  const form = document.getElementById("log-panel");
  form.elements.reps.value = "";
  form.elements.kg.value = "";
  const field = form.elements.exercise;
  field.value = "";
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.focus();
});

// After an Undo, the Undo button for the set now last arrives disabled
// (data-cooldown), so the second tap of a double tap can't remove that set
// too. Enable it once a double tap would be over.
const UNDO_COOLDOWN_MS = 600;
document.addEventListener("htmx:afterSettle", () => {
  for (const button of document.querySelectorAll("[data-cooldown]")) {
    button.removeAttribute("data-cooldown");
    setTimeout(() => (button.disabled = false), UNDO_COOLDOWN_MS);
  }
});

// Ask in our own dialog, not the browser's confirm() box, before a button with
// hx-confirm sends its request. The title is hx-confirm; the rest comes from
// the button's data-confirm-body and data-confirm-action.
const confirmDialog = document.getElementById("confirm");
let pendingRequest = null; // the request the open dialog is asking about

document.addEventListener("htmx:confirm", (event) => {
  const title = event.detail.question;
  if (!title) return; // every request passes through here, most don't ask
  event.preventDefault();
  const button = event.detail.elt;
  document.getElementById("confirm-title").textContent = title;
  document.getElementById("confirm-body").textContent = button.dataset.confirmBody;
  document.getElementById("confirm-action").textContent = button.dataset.confirmAction;
  pendingRequest = event.detail;
  // Escape and Back close the dialog without setting returnValue, so clear
  // the last answer: an earlier confirm mustn't count for this question
  confirmDialog.returnValue = "";
  confirmDialog.showModal();
});

confirmDialog.addEventListener("close", () => {
  if (confirmDialog.returnValue === "confirm") pendingRequest?.issueRequest(true);
  pendingRequest = null;
});

// A tap on the dimmed backdrop cancels any of our dialogs. A dialog has no
// padding of its own, so a click whose target is the dialog itself landed
// outside its content. On document, as the Share dialog is swapped in by HTMX.
document.addEventListener("click", (event) => {
  if (event.target.matches("dialog.dialog")) event.target.close();
});

// Share Workout opens the phone's share sheet with the summary (DAI-9).
// Browsers only allow share() straight after a tap, so the text is already in
// the page (data-summary) rather than fetched here. Most desktop browsers have
// no share sheet, so they get our dialog of other ways to send it instead.
function summaryFor(element) {
  return element.closest("[data-summary]").dataset.summary;
}

// Once the summary has gone somewhere, tell the server, so New Workout stops
// warning that the workout hasn't been shared. Only the top bar comes back, as
// the Share dialog may still be open.
function markShared() {
  htmx
    .ajax("POST", "/shared", { target: "#top-bar", swap: "outerHTML" })
    // E.g. no signal in the gym. The warning stays, which is the safe side
    .catch(() => {});
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-share]");
  if (!button) return;
  if (!navigator.share) {
    document.getElementById("share-options").showModal();
    return;
  }
  // Resolves once an app is picked, not when the message is sent, which is
  // as much as a browser can tell us
  navigator.share({ text: summaryFor(button) }).then(markShared, (error) => {
    // Closing the sheet without picking anything isn't an error
    if (error.name !== "AbortError") throw error;
  });
});

// Copy to Clipboard says "Copied" on itself for a moment; the dialog stays open
const COPIED_MS = 2000;
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;
  await navigator.clipboard.writeText(summaryFor(button));
  markShared();
  button.dataset.label ??= button.textContent;
  button.textContent = "Copied";
  clearTimeout(button.copiedTimer);
  button.copiedTimer = setTimeout(
    () => (button.textContent = button.dataset.label),
    COPIED_MS,
  );
});

// WhatsApp, Email and SMS in the Share dialog count as shared once tapped
document.addEventListener("click", (event) => {
  if (event.target.closest("#share-options a")) markShared();
});
