"""Patch the live homepage: replace the DevStat card with a More tools card that opens a
modal listing DevStat, ClinicalLetter and Consent Forms.

The homepage is not kept in this project, so this reads the live page and writes a patched
copy to `homepage/index.html` for uploading.

Usage:
    python tools/add_homepage_card.py
"""

from __future__ import annotations

import pathlib
import re
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "homepage" / "index.html"
LIVE = "https://dpsoncology.com/"

MORE_TOOLS_CARD = """<a href="#more-tools" class="tool-card card-slate" role="button" aria-haspopup="dialog" aria-controls="more-tools-modal">
        <div class="tool-card-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--text3)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        </div>
        <span class="tag" style="background:#f1f5f9;color:var(--text2);">More</span>
        <h3>More Tools</h3>
        <p>DevStat, ClinicalLetter and Consent Forms — the tools that do not need a card of their own.</p>
      </a>"""

MODAL = """
    <div class="mt-overlay" id="more-tools-modal" role="dialog" aria-modal="true" aria-labelledby="mt-title" hidden>
      <div class="mt-panel" role="document">
        <div class="mt-head">
          <h2 id="mt-title">More tools</h2>
          <button type="button" class="mt-close" id="mt-close" aria-label="Close">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
          </button>
        </div>

        <a class="mt-item" href="./desktop-edition.html" target="_blank" rel="noopener noreferrer">
          <span class="mt-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--amber)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6"/><rect x="12" y="8" width="3" height="10"/><rect x="17" y="5" width="3" height="13"/></svg>
          </span>
          <span class="mt-text">
            <strong>DevStat</strong>
            <small>Medical statistics on your own machine — tests, regression, survival, charts.</small>
          </span>
          <svg class="mt-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>
        </a>

        <a class="mt-item" href="./clinicalletter/">
          <span class="mt-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--nhs-blue)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16v16H4z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>
          </span>
          <span class="mt-text">
            <strong>ClinicalLetter</strong>
            <small>Clinical letters without the retyping — six specialties, your templates, a finished Word file.</small>
          </span>
          <svg class="mt-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>
        </a>

        <a class="mt-item" href="./consent.html">
          <span class="mt-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M15 3v4h4"/><path d="m8.5 14.5 2 2 4-4"/></svg>
          </span>
          <span class="mt-text">
            <strong>Consent Forms</strong>
            <small>Pick a SACT regimen, tick what you discussed, print a file copy and a patient copy.</small>
          </span>
          <svg class="mt-arrow" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>
        </a>

        <p class="mt-foot">No patient details are entered in any of these tools.</p>
      </div>
    </div>
"""

CSS = """
    /* More tools card + modal */
    .tool-card.card-slate { border-top: 3px solid var(--text4); }
    .mt-overlay {
      position: fixed;
      inset: 0;
      z-index: 400;
      background: rgba(15, 23, 42, 0.55);
      display: grid;
      place-items: center;
      padding: 16px;
    }
    .mt-overlay[hidden] { display: none; }
    .mt-panel {
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: 0 20px 50px rgba(15, 23, 42, 0.28);
      width: min(520px, 100%);
      padding: 20px 20px 16px;
    }
    .mt-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
    .mt-head h2 { font-family: 'Merriweather', Georgia, serif; font-size: 1.05rem; font-weight: 700; margin: 0; }
    .mt-close { background: none; border: 0; color: var(--text3); cursor: pointer; padding: 6px; border-radius: 50%; line-height: 0; }
    .mt-close:hover { background: var(--surface2); color: var(--text); }
    .mt-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      text-decoration: none;
      color: var(--text);
      margin-bottom: 10px;
      transition: border-color .18s ease, background .18s ease, transform .18s ease;
    }
    .mt-item:hover { border-color: var(--nhs-mid); background: var(--surface2); transform: translateY(-1px); }
    .mt-icon { flex: none; width: 34px; height: 34px; display: grid; place-items: center; background: var(--surface2); border-radius: var(--radius-sm); }
    .mt-text { display: grid; gap: 2px; flex: 1; min-width: 0; }
    .mt-text strong { font-size: 14.5px; font-weight: 600; }
    .mt-text small { color: var(--text3); font-size: 12.5px; line-height: 1.4; }
    .mt-arrow { color: var(--text4); flex: none; }
    .mt-foot { margin: 12px 2px 2px; font-size: 11.5px; color: var(--text4); }
    body.mt-open { overflow: hidden; }
"""

JS = """
    <script>
      (function () {
        var modal = document.getElementById('more-tools-modal');
        var openers = document.querySelectorAll('[aria-controls="more-tools-modal"]');
        var close = document.getElementById('mt-close');
        if (!modal || !close) return;
        var lastFocus = null;

        function open(event) {
          if (event) event.preventDefault();
          lastFocus = document.activeElement;
          modal.hidden = false;
          document.body.classList.add('mt-open');
          close.focus();
        }
        function shut() {
          modal.hidden = true;
          document.body.classList.remove('mt-open');
          if (lastFocus) lastFocus.focus();
        }

        openers.forEach(function (opener) {
          opener.addEventListener('click', open);
          opener.addEventListener('keydown', function (event) {
            if (event.key === 'Enter' || event.key === ' ') open(event);
          });
        });
        close.addEventListener('click', shut);
        modal.addEventListener('click', function (event) {
          if (event.target === modal) shut();
        });
        document.addEventListener('keydown', function (event) {
          if (event.key === 'Escape' && !modal.hidden) shut();
        });
      })();
    </script>
"""


def main() -> None:
    html = urllib.request.urlopen(
        urllib.request.Request(LIVE, headers={"User-Agent": "Mozilla/5.0"}), timeout=90
    ).read().decode("utf-8")

    heading = html.find("<h3>DevStat Statistics App</h3>")
    if heading < 0:
        raise SystemExit("could not find the DevStat card on the live page")
    anchor_start = html.rfind("<a ", 0, heading)
    anchor_end = html.find("</a>", heading) + len("</a>")

    patched = html[:anchor_start] + MORE_TOOLS_CARD + html[anchor_end:]

    # Two columns on a phone so nine cards stay readable.
    if "@media (max-width: 640px)" not in patched:
        grid_rule = re.search(r"\.tools-grid\s*\{[^}]*\}", patched)
        if grid_rule:
            patched = (
                patched[: grid_rule.end()]
                + "\n    @media (max-width: 640px) {\n"
                + "      .tools-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n"
                + "    }"
                + patched[grid_rule.end() :]
            )

    if "mt-overlay" not in patched.split("</style>")[0]:
        head_end = patched.find("</style>")
        if head_end > 0:
            patched = patched[:head_end] + CSS + patched[head_end:]

    if "more-tools-modal" not in patched.rsplit("</body>", 1)[0].split("<script")[-1]:
        body_end = patched.rfind("</body>")
        patched = patched[:body_end] + MODAL + JS + patched[body_end:]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(patched, encoding="utf-8")

    cards = len(re.findall(r'class="tool-card card-[a-z]+"', patched))
    print(f"wrote {OUT.relative_to(ROOT)}  ({len(patched)//1024} KB)")
    print(f"cards in the grid: {cards}")
    print("modal:", "present" if 'id="more-tools-modal"' in patched else "MISSING")


if __name__ == "__main__":
    main()
