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
document.addEventListener("htmx:afterSettle", showCurrentExercise);
