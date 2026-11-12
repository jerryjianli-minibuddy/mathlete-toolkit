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

  // sample pages: tap one to read it full screen here, with previous and next (Nov 11). Without JS,
  // or without <dialog>, the link simply opens the big image.
  var lb = null, lbItems = [], lbAt = 0;
  function lbShow(i) {
    lbAt = (i + lbItems.length) % lbItems.length;
    var it = lbItems[lbAt];
    lb.querySelector("img").src = it.href;
    lb.querySelector("img").alt = it.alt;
    lb.querySelector(".lb-cap").textContent = it.cap;
    lb.querySelector(".lb-n").textContent = (lbAt + 1) + " / " + lbItems.length;
  }
  function lbBuild() {
    lb = document.createElement("dialog");
    lb.className = "lb";
    lb.setAttribute("aria-label", "Sample pages");
    lb.innerHTML = '<div class="lb-bar"><button type="button" class="lb-btn lb-p" aria-label="Previous page">&lsaquo;</button>' +
      '<span class="lb-n"></span><button type="button" class="lb-btn lb-nx" aria-label="Next page">&rsaquo;</button>' +
      '<button type="button" class="lb-btn lb-x" aria-label="Close">&times;</button></div>' +
      '<div class="lb-body"><img alt=""><p class="lb-cap"></p></div>';
    document.body.appendChild(lb);
    lb.querySelector(".lb-p").addEventListener("click", function () { lbShow(lbAt - 1); });
    lb.querySelector(".lb-nx").addEventListener("click", function () { lbShow(lbAt + 1); });
    lb.querySelector(".lb-x").addEventListener("click", function () { lb.close(); });
    lb.addEventListener("click", function (ev) { if (ev.target === lb) lb.close(); });
    lb.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowLeft") lbShow(lbAt - 1);
      if (ev.key === "ArrowRight") lbShow(lbAt + 1);
    });
  }
  if (window.HTMLDialogElement) document.querySelectorAll(".samples").forEach(function (g) {
    var links = Array.prototype.slice.call(g.querySelectorAll(".sample a"));
    var items = links.map(function (a) {
      var img = a.querySelector("img"), cap = a.parentNode.querySelector("figcaption");
      return { href: a.href, alt: img ? img.alt : "", cap: cap ? cap.textContent.trim() : "" };
    });
    links.forEach(function (a, i) {
      a.addEventListener("click", function (ev) {
        ev.preventDefault();
        if (!lb) lbBuild();
        lbItems = items; lbShow(i);
        lb.showModal();
      });
    });
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

// Browse bar dropdowns (Nov 11): tap opens and closes; on a desktop with a mouse they also open on hover.
// Menus are position: fixed under the bar (the bar scrolls sideways on phones and would clip them).
(function () {
  var dds = Array.prototype.slice.call(document.querySelectorAll("[data-dd]"));
  if (!dds.length) return;
  var wide = window.matchMedia ? matchMedia("(hover: hover) and (min-width: 761px)") : { matches: false };
  var timer = null;
  function btn(d) { return d.querySelector(".dd-btn"); }
  function close(d) { d.classList.remove("open"); btn(d).setAttribute("aria-expanded", "false"); }
  function closeAll(except) { dds.forEach(function (d) { if (d !== except) close(d); }); }
  function place(d) {
    var m = d.querySelector(".dd-menu"), bar = d.closest(".catbar").getBoundingClientRect(), b = btn(d).getBoundingClientRect();
    m.style.top = Math.round(bar.bottom + 6) + "px";
    if (window.innerWidth > 760) {
      m.style.right = "auto";
      m.style.left = Math.round(Math.max(12, Math.min(b.left, window.innerWidth - m.offsetWidth - 12))) + "px";
    } else { m.style.left = "10px"; m.style.right = "10px"; }
  }
  function open(d) { closeAll(d); d.classList.add("open"); btn(d).setAttribute("aria-expanded", "true"); place(d); }
  dds.forEach(function (d) {
    btn(d).addEventListener("click", function (ev) {
      ev.preventDefault();
      if (d.classList.contains("open") && !wide.matches) close(d); else open(d);
    });
    d.addEventListener("mouseenter", function () { if (!wide.matches) return; clearTimeout(timer); open(d); });
    d.addEventListener("mouseleave", function () { if (!wide.matches) return; timer = setTimeout(function () { close(d); }, 250); });
  });
  document.addEventListener("click", function (ev) { if (!ev.target.closest("[data-dd]")) closeAll(); });
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "Escape") return;
    var o = dds.filter(function (d) { return d.classList.contains("open"); })[0];
    if (o) { close(o); btn(o).focus(); }
  });
  window.addEventListener("resize", function () { closeAll(); });
  window.addEventListener("scroll", function () { dds.forEach(function (d) { if (d.classList.contains("open")) { if (wide.matches) place(d); else close(d); } }); }, { passive: true });
  var bar = document.querySelector(".cat-in");
  if (bar) bar.addEventListener("scroll", function () { closeAll(); }, { passive: true });
})();

/* /free: pick a contest and a grade; the pick shows its free download next to the paid practice tests (Nov 11, Jian: the diagnostic
   should be specific to the contest). ?contest=kangaroo&grade=5 preselects. A pick with no test says Coming soon. */
(function () {
  var box = document.querySelector("[data-fpick]");
  if (!box) return;
  var ready = JSON.parse(box.getAttribute("data-ready") || "{}");
  var cbs = box.querySelectorAll("[data-contest]"), gbs = box.querySelectorAll("[data-grade]");
  var msg = box.querySelector(".fpick-msg");
  var st = window.kmmPick = { contest: null, grade: null, key: null, label: "" };
  var res = document.querySelectorAll(".fres");
  function paint() {
    var r = ready[st.contest] || {};
    /* Nov 12, Jian: Kangaroo and Noetic only up to Grade 5, so higher grade tiles hide for them. */
    var cb = st.contest && box.querySelector('[data-contest="' + st.contest + '"]');
    var max = cb ? +(cb.getAttribute("data-max") || 12) : 12;
    if (st.grade && +st.grade > max) st.grade = null;
    Array.prototype.forEach.call(cbs, function (b) {
      var on = b.getAttribute("data-contest") === st.contest;
      b.classList.toggle("pk-on", on); b.setAttribute("aria-pressed", on ? "true" : "false");
      b.classList.toggle("pk-ready", !!ready[b.getAttribute("data-contest")]);
    });
    Array.prototype.forEach.call(gbs, function (b) {
      var g = b.getAttribute("data-grade"), ok = !!r[g], on = g === st.grade;
      b.style.display = +g > max ? "none" : "";
      b.classList.toggle("gp-on", ok); b.classList.toggle("gp-sel", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      b.querySelector("span").textContent = !st.contest ? "Pick a contest" : ok ? "Free test" : "Coming soon";
    });
    var hit = r[st.grade];
    st.key = hit ? hit[0] : null; st.label = hit ? hit[1] : "";
    msg.className = "fpick-msg" + (hit ? " ok" : st.contest && st.grade ? " soon" : "");
    msg.textContent = hit ? "Your test: " + hit[1] + "."
      : st.contest && st.grade ? "This test is coming soon. Pick another contest or grade."
      : st.contest ? "Now pick a grade." : "Pick a contest and a grade.";
    Array.prototype.forEach.call(res, function (d) { d.hidden = d.getAttribute("data-key") !== st.key; });
  }
  Array.prototype.forEach.call(cbs, function (b) {
    b.addEventListener("click", function () { st.contest = b.getAttribute("data-contest"); paint(); });
  });
  Array.prototype.forEach.call(gbs, function (b) {
    b.addEventListener("click", function () { st.grade = b.getAttribute("data-grade"); paint(); });
  });
  var q = new URLSearchParams(location.search);
  if (q.get("contest") && box.querySelector('[data-contest="' + q.get("contest").replace(/[^a-z0-9]/g, "") + '"]')) st.contest = q.get("contest").replace(/[^a-z0-9]/g, "");
  if (/^\d{1,2}$/.test(q.get("grade") || "")) st.grade = q.get("grade");
  paint();
})();

/* Print buttons (cheat sheet) */
(function () {
  Array.prototype.forEach.call(document.querySelectorAll("[data-print]"), function (b) {
    b.addEventListener("click", function () { window.print(); });
  });
})();

/* Contest countdown at the top of the home page (Nov 12). Each contest carries its events; the soonest one
   (open windows first) fills the big tiles and ticks every second; the rest are small cards, soonest first. */
(function () {
  var box = document.querySelector("[data-countdown]");
  if (!box) return;
  var feat = box.querySelector("[data-cd-feat]"), list = box.querySelector(".cdx-list");
  var all = [feat].concat(Array.prototype.slice.call(list.querySelectorAll(".cdx-card")));
  var items = all.map(function (el) {
    return { name: el.getAttribute("data-name"), note: el.getAttribute("data-note"), href: el.getAttribute("data-href"),
             evs: JSON.parse(el.getAttribute("data-events") || "[]") };
  });
  function day(s, end) { var p = s.split("-"); return end ? new Date(+p[0], p[1] - 1, +p[2], 23, 59, 59) : new Date(+p[0], p[1] - 1, +p[2]); }
  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  function short(ms) {
    var m = Math.max(0, Math.floor(ms / 60000)), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60);
    return d ? d + "d " + h + "h" : h + "h " + (m % 60) + "m";
  }
  function set(el, f, v, attr) { var t = el.querySelector('[data-f="' + f + '"]'); if (t) { if (attr) t.setAttribute(attr, v); else t.textContent = v; } }
  function tick() {
    var now = new Date(), live = [];
    items.forEach(function (it) {
      var ev = it.evs.filter(function (x) { return day(x[1], true) >= now; })[0];
      if (!ev) return;
      var s = day(ev[0]), e = day(ev[1], true), open = s <= now;
      live.push({ it: it, ev: ev, open: open, target: open ? e : s, key: open ? 0 : s.getTime(), single: ev[0] === ev[1] });
    });
    live.sort(function (a, b) { return a.key - b.key; });
    if (!live.length) { box.hidden = true; return; }
    var f = live[0], left = Math.max(0, Math.floor((f.target - now) / 1000));
    feat.classList.toggle("cdx-open", f.open);
    set(feat, "badge", f.open ? (f.single ? "Today" : "Open now") : "Next up");
    set(feat, "name", f.it.name); set(feat, "when", f.ev[2]); set(feat, "note", f.it.note);
    set(feat, "cap", f.open ? (f.single ? "ends in" : "window closes in") : "starts in");
    feat.querySelector('[data-f="href"]').setAttribute("href", f.it.href);
    var u = { d: Math.floor(left / 86400), h: Math.floor(left % 86400 / 3600), m: Math.floor(left % 3600 / 60), s: left % 60 };
    ["d", "h", "m", "s"].forEach(function (k) { feat.querySelector('[data-u="' + k + '"]').textContent = k === "d" ? u.d : pad(u[k]); });
    var cards = list.querySelectorAll(".cdx-card");
    live.slice(1).forEach(function (x, i) {
      var c = cards[i];
      if (!c) return;
      c.hidden = false;
      c.classList.toggle("cdx-open", x.open);
      set(c, "name", x.it.name); set(c, "when", x.ev[2]);
      set(c, "left", x.open ? "Open now, " + short(x.target - now) + " left" : "Starts in " + short(x.target - now));
    });
    for (var k = live.length - 1; k < cards.length; k++) cards[k].hidden = true;
  }
  tick();
  setInterval(tick, 1000);
})();
