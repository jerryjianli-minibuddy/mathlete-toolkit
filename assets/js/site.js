(function () {
  // mobile menu
  var menu = document.querySelector(".menu"), nav = document.getElementById("nav");
  if (menu && nav) menu.addEventListener("click", function () {
    var open = nav.classList.toggle("open");
    menu.setAttribute("aria-expanded", open ? "true" : "false");
  });

  // click-to-play YouTube (loads the player only when asked, so pages stay fast)
  document.querySelectorAll("button.player[data-id]").forEach(function (b) {
    b.addEventListener("click", function () {
      var f = document.createElement("iframe");
      f.src = "https://www.youtube.com/embed/" + b.dataset.id + "?autoplay=1&rel=0&playsinline=1";
      f.title = b.getAttribute("aria-label") || "YouTube video";
      f.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
      f.allowFullscreen = true;
      f.referrerPolicy = "strict-origin-when-cross-origin";
      var d = document.createElement("div");
      d.className = "player";
      d.appendChild(f);
      b.replaceWith(d);
    });
  });

  // lesson filters
  var filters = document.querySelector(".filters");
  if (!filters) return;
  var cards = Array.prototype.slice.call(document.querySelectorAll(".grid .card"));
  var cBtns = filters.querySelectorAll("button[data-contest]");
  var fam = document.getElementById("fam"), liveOnly = document.getElementById("liveonly");
  var count = document.querySelector(".count");
  var state = { contest: "", fam: "" };
  try {
    var p = new URLSearchParams(location.search);
    state.contest = p.get("contest") || ""; state.fam = p.get("topic") || "";
  } catch (e) {}
  function apply() {
    var n = 0;
    cards.forEach(function (c) {
      var ok = (!state.contest || (" " + c.dataset.contests + " ").indexOf(" " + state.contest + " ") > -1)
        && (!state.fam || c.dataset.family === state.fam)
        && (!liveOnly.checked || !c.classList.contains("is-soon"));
      c.hidden = !ok; if (ok) n++;
    });
    cBtns.forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.contest === state.contest ? "true" : "false"); });
    fam.value = state.fam;
    count.textContent = n + (n === 1 ? " lesson" : " lessons");
  }
  cBtns.forEach(function (b) { b.addEventListener("click", function () { state.contest = b.dataset.contest; apply(); }); });
  fam.addEventListener("change", function () { state.fam = fam.value; apply(); });
  liveOnly.addEventListener("change", apply);
  apply();
})();
