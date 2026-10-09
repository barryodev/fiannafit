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

// A tap on the dimmed backdrop cancels. The dialog has no padding of its own,
// so a click whose target is the dialog itself landed outside its content.
confirmDialog.addEventListener("click", (event) => {
  if (event.target === confirmDialog) confirmDialog.close();
});
