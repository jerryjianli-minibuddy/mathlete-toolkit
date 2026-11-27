/* Key Move Math parent sign-in (Nov 27, Jian: "Enable Google login", "Both").
   Parents sign in with Google to download the PDFs; lessons and topic pages stay open.
   Firebase Auth + Firestore (free Spark plan). Keeps only name, email, the opt-in choice,
   and which lessons and downloads were used. Loaded only when window.KMM_FB has a config. */
(function () {
  "use strict";
  var C = window.KMM_FB;
  if (!C || !C.apiKey) return;
  var V = "10.12.2", B = "https://www.gstatic.com/firebasejs/" + V + "/";
  var LS = "kmm_signed", ready = null;

  function load(src) {
    return new Promise(function (ok, bad) {
      var s = document.createElement("script");
      s.src = src; s.onload = ok; s.onerror = bad;
      document.head.appendChild(s);
    });
  }
  function fb() {
    if (!ready) {
      ready = load(B + "firebase-app-compat.js")
        .then(function () { return Promise.all([load(B + "firebase-auth-compat.js"), load(B + "firebase-firestore-compat.js")]); })
        .then(function () {
          firebase.initializeApp(C);
          return new Promise(function (ok) {
            var stop = firebase.auth().onAuthStateChanged(function (u) { stop(); setSigned(!!u); ok(u); });
          });
        });
    }
    return ready;
  }
  function signedHint() { try { return localStorage.getItem(LS) === "1"; } catch (e) { return false; } }
  function setSigned(v) { try { v ? localStorage.setItem(LS, "1") : localStorage.removeItem(LS); } catch (e) {} navLink(v); }
  function doc(u) { return firebase.firestore().collection("parents").doc(u.uid); }
  function now() { return firebase.firestore.FieldValue.serverTimestamp(); }
  function key(s) { return String(s).replace(/[^A-Za-z0-9-]/g, "_").slice(0, 120); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  function record(kind, id, label) {
    return fb().then(function (u) {
      if (!u) return;
      var o = { updated: now() };
      o[kind + "." + key(id)] = { label: String(label || id).slice(0, 160), at: now() };
      return doc(u).update(o).catch(function () {});
    }).catch(function () {});
  }

  /* Header link: "Parent sign-in" or "My progress" */
  function navLink(on) {
    var bar = document.querySelector(".cat-in");
    if (!bar) return;
    var a = document.getElementById("au-nav");
    if (!a) { a = document.createElement("a"); a.id = "au-nav"; a.className = "cat"; a.href = "/my-progress/"; bar.appendChild(a); }
    a.textContent = on ? "My progress" : "Parent sign-in";
  }

  /* Sign-in dialog */
  function dialog(title) {
    return new Promise(function (resolve) {
      var back = document.createElement("div");
      back.className = "au-back";
      back.innerHTML =
        '<div class="au-box" role="dialog" aria-modal="true" aria-labelledby="au-h">' +
        '<button type="button" class="au-x" aria-label="Close">&times;</button>' +
        '<p class="au-kick">For parents and guardians</p>' +
        '<h2 id="au-h">' + esc(title || "Sign in to download") + "</h2>" +
        "<p>Sign in with Google to get the PDF. We'll also keep a list of the lessons and tests your child has used, so you can see where they are.</p>" +
        '<label class="au-opt"><input type="checkbox" id="au-opt"> Email me new practice tests and study tips. Unsubscribe anytime.</label>' +
        '<button type="button" class="au-g"><svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.6 5.4 2.7 13.3l7.9 6.1C12.5 13.6 17.8 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.7 6c4.5-4.2 6.9-10.3 6.9-17.7z"/><path fill="#FBBC05" d="M10.6 28.6c-.5-1.4-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.1C1 16.6 0 20.2 0 24s1 7.4 2.7 10.7l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.7-6c-2.2 1.5-5 2.3-8.2 2.3-6.2 0-11.5-4.1-13.4-9.9l-7.9 6.1C6.6 42.6 14.6 48 24 48z"/></svg><span>Continue with Google</span></button>' +
        '<p class="au-err" hidden></p>' +
        '<p class="au-fine">We keep only your name and email from Google, plus which lessons and downloads were used. No child accounts. Kids, please ask a parent to sign in. <a href="/privacy/">Privacy</a></p>' +
        "</div>";
      document.body.appendChild(back);
      var g = back.querySelector(".au-g"), err = back.querySelector(".au-err");
      function close(v) { back.remove(); document.removeEventListener("keydown", onKey); resolve(v); }
      function onKey(ev) { if (ev.key === "Escape") close(null); }
      document.addEventListener("keydown", onKey);
      back.addEventListener("click", function (ev) { if (ev.target === back) close(null); });
      back.querySelector(".au-x").addEventListener("click", function () { close(null); });
      g.addEventListener("click", function () {
        var opt = back.querySelector("#au-opt").checked;
        g.disabled = true; err.hidden = true;
        signIn(opt).then(function (u) { close(u); }).catch(function (e) {
          g.disabled = false;
          if (e && e.code === "auth/popup-closed-by-user") return;
          err.textContent = "Sign-in didn't finish. Please try again, or allow pop-ups for this site.";
          err.hidden = false;
        });
      });
      g.focus();
    });
  }

  function signIn(optIn) {
    return fb().then(function () {
      var p = new firebase.auth.GoogleAuthProvider();
      p.setCustomParameters({ prompt: "select_account" });
      return firebase.auth().signInWithPopup(p);
    }).then(function (res) {
      var u = res.user, ref = doc(u);
      return ref.get().then(function (snap) {
        var o = { name: u.displayName || "", email: u.email || "", updated: now() };
        if (!snap.exists) { o.created = now(); o.optIn = !!optIn; o.downloads = {}; o.lessons = {}; o.done = {}; }
        else if (optIn) { o.optIn = true; }
        return ref.set(o, { merge: true });
      }).then(function () { setSigned(true); return u; });
    });
  }

  /* Free downloads: on-site PDFs and the Drive diagnostic links */
  function isDownload(a) {
    var h = a.getAttribute("href") || "";
    if (/drive\.google\.com\/uc\?export=download/.test(h)) return true;
    try { var url = new URL(h, location.href); return url.origin === location.origin && /\.pdf$/i.test(url.pathname); } catch (e) { return false; }
  }
  function isLesson(a) { return /youtube\.com\/(watch\?v=|shorts\/)|youtu\.be\//.test(a.href || ""); }
  function videoId(a) { var m = (a.href || "").match(/(?:v=|shorts\/|youtu\.be\/)([\w-]{11})/); return m && m[1]; }
  function labelOf(a) { return (a.getAttribute("data-label") || a.textContent || "").replace(/\s+/g, " ").trim() + " | " + document.title.split(" | ")[0]; }
  function go(a) { if (a.target === "_blank") window.open(a.href, "_blank", "noopener"); else location.href = a.href; }

  document.addEventListener("click", function (ev) {
    if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    var a = ev.target.closest && ev.target.closest("a[href]");
    if (!a) return;
    if (isDownload(a)) {
      ev.preventDefault();
      var label = labelOf(a), id = (a.getAttribute("href") || "").split("/").pop().split("?")[0] || a.href;
      fb().then(function (u) { return u || dialog(); }).then(function (u) {
        if (!u) return;
        var t = setTimeout(function () { go(a); }, 900);
        record("downloads", id, label).then(function () { clearTimeout(t); go(a); });
      });
    } else if (isLesson(a) && signedHint()) {
      ev.preventDefault();
      var t2 = setTimeout(function () { go(a); }, 800);
      record("lessons", videoId(a) || a.href, labelOf(a)).then(function () { clearTimeout(t2); go(a); });
    }
  });

  /* A lesson page visit counts as a lesson looked at (signed-in parents only) */
  var lm = document.querySelector('meta[name="kmm-lesson"]');
  if (lm && signedHint()) record("lessons", lm.content, document.title.split(" | ")[0]);

  navLink(signedHint());
  if (signedHint()) fb();

  /* /my-progress/ and /admin/parents/ hooks */
  window.KMM_AUTH = { fb: fb, dialog: dialog, doc: doc, esc: esc, now: now, setSigned: setSigned };
  document.dispatchEvent(new Event("kmm-auth-ready"));
})();
