/* 당근영어 PWA 설치 안내 배너 — busan-travel 스타일. 자가주입(페이지 DOM 불요).
   갤럭시/Chrome/Samsung Internet = beforeinstallprompt 로 [설치] 버튼,
   iOS = 안내문구, 인앱브라우저=생략, 설치/standalone=숨김, 닫기 영구기억. */
(function () {
  var standalone = window.matchMedia("(display-mode: standalone)").matches ||
                   window.navigator.standalone === true;
  if (standalone) return;
  if (localStorage.getItem("pwa_banner_dismissed") === "1") return;

  var deferred = null, bar = null, installBtn = null;

  function build() {
    if (bar) return;
    bar = document.createElement("div");
    bar.id = "pwa-install-bar";
    bar.style.cssText = "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);" +
      "z-index:9999;display:none;align-items:center;gap:12px;max-width:520px;" +
      "width:calc(100% - 28px);background:#161b22;color:#e6edf3;border:1px solid #2a3340;" +
      "border-radius:14px;padding:11px 14px;box-shadow:0 10px 30px rgba(0,0,0,.45);" +
      'font-family:-apple-system,"Segoe UI",Roboto,"Malgun Gothic",sans-serif';
    bar.innerHTML =
      '<img src="icon-192.png" alt="" width="38" height="38" style="border-radius:9px;flex-shrink:0">' +
      '<div style="flex:1;min-width:0;line-height:1.4">' +
        '<div style="font-weight:700;font-size:14px">🥕 당근영어를 앱으로 추가</div>' +
        '<div id="pwa-bar-sub" style="font-size:12px;color:#9aa4b2">홈 화면에서 바로 열어요</div>' +
      '</div>' +
      '<button id="pwa-install-btn" style="display:none;background:linear-gradient(135deg,#f7902f,#f5a623);' +
        'color:#241400;border:0;border-radius:9px;padding:9px 15px;font-weight:700;font-size:13px;cursor:pointer;flex-shrink:0">설치</button>' +
      '<button id="pwa-dismiss" aria-label="닫기" style="background:transparent;color:#7d8794;border:0;' +
        'font-size:20px;line-height:1;cursor:pointer;padding:2px 4px;flex-shrink:0">&times;</button>';
    document.body.appendChild(bar);
    installBtn = bar.querySelector("#pwa-install-btn");
    bar.querySelector("#pwa-dismiss").onclick = function () {
      hide(); localStorage.setItem("pwa_banner_dismissed", "1");
    };
    installBtn.onclick = async function () {
      if (!deferred) return;
      deferred.prompt();
      try { await deferred.userChoice; } catch (e) {}
      deferred = null; hide();
    };
  }
  function show() { build(); bar.style.display = "flex"; }
  function hide() { if (bar) bar.style.display = "none"; }

  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault(); deferred = e; show();
    if (installBtn) installBtn.style.display = "inline-block";
  });
  window.addEventListener("appinstalled", function () {
    localStorage.setItem("pwa_banner_dismissed", "1"); hide();
  });

  window.addEventListener("load", function () {
    setTimeout(function () {
      if (deferred) return;                       // 이미 [설치] 버튼형으로 노출됨
      var ua = navigator.userAgent || "";
      if (/KAKAOTALK|NAVER|Instagram|FBAN|FBAV|Line|DaumApps/i.test(ua)) return;  // 인앱=설치불가
      var ios = /iPhone|iPad|iPod/i.test(ua);
      show();
      var sub = document.getElementById("pwa-bar-sub");
      if (sub) sub.textContent = ios ? '공유 → "홈 화면에 추가"' : '메뉴(⋮) → "앱 설치 / 홈 화면에 추가"';
    }, 2500);
  });
})();
