# Security and privacy notes

## Data profile

Special-category / health data. The app handles patient name, date of birth, NHS number,
consultant name, which side effects were discussed, free-text notes, and a signature
image (as vector strokes).

## Trust boundaries

- **Client/browser** — the only place data exists. Wasm linear memory plus the DOM.
- **Application server** — none. The app is static files; there is no endpoint to call.
- **Database/storage** — none. No cookies, no localStorage, no IndexedDB.
- **External APIs/LLMs** — none at runtime. (Form text was extracted offline during
  development, not in the browser.)
- **Cloud deployment** — `trunk build --release` produces static assets; hosting is the
  clinic's intranet or a local machine.
- **Administrator/support access** — none; there is nothing to access remotely.

## Controls confirmed

- Content-Security-Policy in `index.html`: `default-src 'none'`, `connect-src 'self'`,
  `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'`, `img-src 'self' data:`.
  `'self'` for connect is unavoidable (the browser fetches the wasm module through it) and
  `'unsafe-inline'` is needed by the Trunk loader; every external origin — fonts, images,
  frames, scripts — is still blocked. There is no server endpoint, so the only reachable
  URL is the static bundle already served.
- No networking primitives in the dependency tree and none in the application source.

- No client-side persistence of any kind. Every PHI input sets `autocomplete="off"`.
- `zeroize` on the patient struct; **Clear** replaces the whole `AppState`, and the DOM
  is re-rendered from the empty state.
- Signature stored as coordinates in a fixed 600 × 170 space; printed as SVG paths.

## Open risks

- **Risk level:** Medium
- **Risk:** Printing is a disclosure path the app does not control. The print spooler,
  any "save as PDF", and the paper itself retain the data after the tab is closed.
- **Mitigation:** the printed footer names the source form and version; local process
  should treat the printed copies as the record of disclosure.
- **Decision/owner:** clinician / Trust information governance.

- **Risk level:** Low
- **Risk:** Browser session restore or the back/forward cache could keep a rendered page
  alive after navigation, though no state is persisted.
- **Mitigation:** **Clear** button; instruct staff to close the tab at the end of the
  session; do not deploy as an installed PWA with an offline cache.
- **Decision/owner:** deploying team.

- **Risk level:** Low
- **Risk:** Wasm linear memory is freed by the browser when the tab closes, but the
  operating system may have paged parts of it to disk beforehand.
- **Mitigation:** none available from inside the page. Use an encrypted, Trust-managed
  machine.
- **Decision/owner:** Trust IT.

## Claims to avoid

- Do not claim "UK GDPR compliant", "DTAC approved", or "NHS approved". This is a
  documentation aid built against public forms; compliance depends on local deployment,
  DPIA and clinical governance sign-off.
- Do not claim the app replaces the national consent form. The printed output is a record
  of the discussion, citing the form and its version.

## Clinical content caveat

The wording in `sources/content.json` was transcribed from the published PDFs and checked
against `sources/clean/*.txt`. Before clinical use, a clinician with local responsibility
must confirm each list against the current edition of the form and confirm that the
printed version string matches it. CRUK states that their forms should be used in their
entirety and points to separate guidance on electronic consent; that guidance should be
reviewed before this record is adopted as a local process.
