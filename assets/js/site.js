(function () {
  // phones: the header slides away while scrolling down and comes back on any scroll up, so the
  // browse bar stays one flick away without covering the page (Nov 11)
  var top = document.querySelector(".top"), lastY = window.scrollY || 0, ticking = false;
  var phone = window.matchMedia ? matchMedia("(max-width: 760px)") : { matches: false };
  function onScroll() {
    ticking = false;
    var y = window.scrollY || 0;
    if (top) {
      var hide = phone.matches && y > 160 && y > lastY + 4 && !top.contains(document.activeElement);
      if (hide) top.classList.add("top-hide");
      else if (y < lastY - 4 || y <= 160) top.classList.remove("top-hide");
    }
    lastY = y;
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  if (top) top.addEventListener("focusin", function () { top.classList.remove("top-hide"); });

  // phones: the bottom free-test bar hides while the page's own free-test button is on screen
  var bar = document.getElementById("mcta"), watch = document.querySelectorAll("[data-cta-watch]");
  if (bar && watch.length && "IntersectionObserver" in window) {
    var seen = new Set();
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) { if (en.isIntersecting) seen.add(en.target); else seen.delete(en.target); });
      bar.classList.toggle("mcta-off", seen.size > 0);
    });
    watch.forEach(function (w) { io.observe(w); });
  }

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

  // lesson search + filters (lessons/). Without JS every lesson shows and the search box is a plain form.
  var filters = document.querySelector(".filters");
  if (!filters) return;
  var cards = Array.prototype.slice.call(document.querySelectorAll(".grid .card"));
  var cBtns = Array.prototype.slice.call(filters.querySelectorAll("button[data-contest]"));
  var fam = document.getElementById("fam"), liveOnly = document.getElementById("liveonly");
  var q = document.getElementById("q"), form = filters.querySelector("form.f-search");
  var count = document.querySelector(".count"), empty = document.querySelector(".f-empty");
  var total = cards.length;

  // search helpers: same normalizing as norm() in build.py
  var STOP = { a: 1, an: 1, the: 1, to: 1, of: 1, and: 1, or: 1, "in": 1, on: 1, "for": 1, "with": 1, how: 1, what: 1, is: 1, "do": 1, i: 1, my: 1 };
  function norm(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9#]+/g, " ").trim(); }
  function tokens(s) { return norm(s).split(" ").filter(function (w) { return w && !STOP[w]; }); }
  function hit(hay, w) {
    if (w.charAt(0) === "#") return hay.indexOf(" " + w + " ") > -1; // tool number: whole word
    if (hay.indexOf(w) > -1) return true;
    return w.length > 3 && w.slice(-1) === "s" && hay.indexOf(w.slice(0, -1)) > -1; // "digits" finds "digit"
  }
  function matches(hay, toks) {
    hay = " " + hay + " ";
    for (var i = 0; i < toks.length; i++) if (!hit(hay, toks[i])) return false;
    return true;
  }
  // end search helpers

  var state = { contest: "", fam: "", q: "", live: false };
  try {
    var p = new URLSearchParams(location.search);
    state.contest = p.get("contest") || ""; state.fam = p.get("topic") || "";
    state.q = p.get("q") || ""; state.live = p.get("live") === "1";
  } catch (e) {}
  if (!cBtns.some(function (b) { return b.dataset.contest === state.contest; })) state.contest = "";
  if (state.fam && !Array.prototype.some.call(fam.options, function (o) { return o.value === state.fam; })) state.fam = "";
  q.value = state.q; liveOnly.checked = state.live;

  function syncUrl() {
    try {
      var p = new URLSearchParams();
      if (state.q.trim()) p.set("q", state.q.trim());
      if (state.contest) p.set("contest", state.contest);
      if (state.fam) p.set("topic", state.fam);
      if (state.live) p.set("live", "1");
      var s = p.toString();
      history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + location.hash);
    } catch (e) {}
  }
  function apply() {
    var n = 0, toks = tokens(state.q);
    cards.forEach(function (c) {
      var ok = (!state.contest || (" " + c.dataset.contests + " ").indexOf(" " + state.contest + " ") > -1)
        && (!state.fam || c.dataset.family === state.fam)
        && (!state.live || !c.classList.contains("is-soon"))
        && (!toks.length || matches(c.dataset.search || "", toks));
      c.hidden = !ok; if (ok) n++;
    });
    cBtns.forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.contest === state.contest ? "true" : "false"); });
    fam.value = state.fam;
    var filtered = n < total;
    count.textContent = filtered ? n + " of " + total + " lessons" : n + (n === 1 ? " lesson" : " lessons");
    if (empty) empty.hidden = n > 0;
    syncUrl();
  }
  cBtns.forEach(function (b) { b.addEventListener("click", function () { state.contest = b.dataset.contest; apply(); }); });
  fam.addEventListener("change", function () { state.fam = fam.value; apply(); });
  liveOnly.addEventListener("change", function () { state.live = liveOnly.checked; apply(); });
  q.addEventListener("input", function () { state.q = q.value; apply(); });
  if (form) form.addEventListener("submit", function (ev) { ev.preventDefault(); state.q = q.value; apply();
    // on phones, close the keyboard so the results show; keep focus put for keyboard users
    if (window.matchMedia && matchMedia("(pointer: coarse)").matches) q.blur();
  });
  document.querySelectorAll("[data-clear]").forEach(function (b) {
    b.addEventListener("click", function () {
      state = { contest: "", fam: "", q: "", live: false };
      q.value = ""; liveOnly.checked = false;
      apply(); q.focus();
    });
  });
  apply();
})();
