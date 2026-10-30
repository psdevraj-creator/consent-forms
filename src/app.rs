//! The single screen: choose the form, tick what was discussed, print both copies.
//!
//! The catalogue of regimens is compiled in; each form's wording, tick coordinates and PDF
//! are fetched when it is selected. No patient details and no signature are collected — they
//! are written by hand on the printed form.

use std::rc::Rc;

use wasm_bindgen_futures::spawn_local;
use web_sys::{HtmlSelectElement, HtmlTextAreaElement};
use yew::prelude::*;

use crate::browser;
use crate::components::side_effects::SideEffectList;
use crate::data::{Catalogue, TherapyType};
use crate::document;
use crate::forms::{FormData, Statement};
use crate::loader::{self, Loaded};
use crate::model::{reduce, Action, AppState};

fn select_value(event: &Event) -> String {
    event
        .target_dyn_into::<HtmlSelectElement>()
        .map(|select| select.value())
        .unwrap_or_default()
}

fn textarea_value(event: &InputEvent) -> String {
    event
        .target_dyn_into::<HtmlTextAreaElement>()
        .map(|area| area.value())
        .unwrap_or_default()
}

#[component]
pub fn App() -> Html {
    let catalogue = use_memo((), |_| Catalogue::embedded().map(Rc::new));

    match &*catalogue {
        Ok(catalogue) => html! { <Workspace catalogue={catalogue.clone()} /> },
        Err(error) => html! {
            <div class="fatal">
                <h1>{"The form list could not be read"}</h1>
                <p>{format!("This build is broken, not your machine: {error}")}</p>
            </div>
        },
    }
}

#[derive(Properties, PartialEq)]
struct WorkspaceProps {
    catalogue: Rc<Catalogue>,
}

#[component]
fn Workspace(props: &WorkspaceProps) -> Html {
    let catalogue = props.catalogue.clone();
    let state = use_state(|| {
        let mut initial = AppState::default();
        let therapies = catalogue.therapies();
        if therapies.len() == 1 {
            initial.therapy = Some(therapies[0]);
        }
        initial
    });
    let purge_armed = use_state(|| false);
    let started = use_state(|| false);
    let loaded = use_state(|| None::<Rc<Loaded>>);
    let loading = use_state(|| false);
    let error = use_state(|| None::<String>);
    let notice = use_state(|| None::<String>);
    let query = use_state(String::new);

    let dispatch = {
        let state = state.clone();
        Callback::from(move |action: Action| {
            let current = Rc::new((*state).clone());
            let next = reduce(&current, action);
            state.set((*next).clone());
        })
    };

    // Fetch the selected form's data and PDF.
    {
        let template_id = state.template_id.clone();
        let loaded = loaded.clone();
        let loading = loading.clone();
        let error = error.clone();
        use_effect_with(template_id.clone(), move |id: &Option<String>| {
            let Some(id) = id.clone() else {
                loaded.set(None);
                loading.set(false);
                error.set(None);
                return;
            };
            loading.set(true);
            error.set(None);
            spawn_local(async move {
                match loader::load(&id).await {
                    Ok(result) => loaded.set(Some(Rc::new(result))),
                    Err(message) => {
                        error.set(Some(message));
                        loaded.set(None);
                    }
                }
                loading.set(false);
            });
        });
    }

    let template_id = state.template_id.clone();
    let therapy = state.therapy;
    let summary = template_id
        .as_deref()
        .and_then(|id| catalogue.form(id))
        .cloned();
    let form: Option<Rc<Loaded>> = (*loaded).clone();

    let on_purge = {
        let purge_armed = purge_armed.clone();
        let dispatch = dispatch.clone();
        Callback::from(move |_| {
            if *purge_armed {
                dispatch.emit(Action::Purge);
                purge_armed.set(false);
            } else {
                purge_armed.set(true);
            }
        })
    };

    let blank = use_state(|| false);
    let on_print = {
        let loaded = form.clone();
        let state = state.clone();
        let notice = notice.clone();
        let blank = *blank;
        Callback::from(move |_: MouseEvent| {
            let Some(form) = loaded.as_ref() else {
                return;
            };
            let built = if blank {
                document::build_blank_with_patient_copy(form)
            } else {
                document::build_with_patient_copy(form, &state)
            };
            // A two-copy PDF is always larger than the form itself; if it is not, nothing was
            // drawn. Refuse to open a blank page that looks like a printing fault.
            if !blank {
                match &built {
                    Ok(bytes) if bytes.len() <= form.pdf.len() => {
                        notice.set(Some(
                            format!(
                                "Nothing was drawn on this computer, so no PDF was opened.
                                 Please report this line: build {} · form {} · {} side effects
                                 and {} declarations selected · PDF {} bytes (form {} bytes).",
                                crate::BUILD,
                                form.data.id,
                                state.reviewed.len(),
                                state.declared.len(),
                                bytes.len(),
                                form.pdf.len()
                            ),
                        ));
                        return;
                    }
                    _ => {}
                }
            }
            match built {
                Ok(bytes) => {
                    let opened = browser::open_pdf(&bytes);
                    // Say exactly what was printed. If the counts are zero, the ticks never
                    // reached the form and the clinician can see that before handing it over.
                    let ticks = format!(
                        "{} side effects and {} declarations",
                        state.reviewed.len(),
                        state.declared.len()
                    );
                    notice.set(Some(if !opened {
                        "The browser blocked the new tab — allow pop-ups for this page, or use
                         “Save a copy to this computer instead”."
                            .to_owned()
                    } else if blank {
                        "Two blank copies are ready: the file copy, then the patient copy. Print
                         from the PDF viewer and complete every box by hand."
                            .to_owned()
                    } else {
                        format!(
                            "Two copies are ready with {ticks} ticked: the file copy, then the
                             patient copy. Print from the PDF viewer, then write the patient
                             details and signature by hand."
                        )
                    }));
                }
                Err(message) => notice.set(Some(message)),
            }
        })
    };

    let on_download = {
        let loaded = form.clone();
        let state = state.clone();
        let notice = notice.clone();
        let template_id = template_id.clone();
        Callback::from(move |_: MouseEvent| {
            let Some(form) = loaded.as_ref() else {
                return;
            };
            match document::build(form, &state) {
                Ok(bytes) => {
                    let name = format!(
                        "consent-{}.pdf",
                        template_id.as_deref().unwrap_or("form")
                    );
                    let saved = browser::save_pdf(&bytes, &name);
                    notice.set(Some(if saved {
                        format!("{name} saved to your downloads.")
                    } else {
                        "The browser blocked the download.".to_owned()
                    }));
                }
                Err(message) => notice.set(Some(message)),
            }
        })
    };

    html! {
        <div class="app">
            <Header
                on_print={on_print.clone()}
                {on_purge}
                purge_armed={*purge_armed}
                can_print={form.is_some()}
            />

            <main class="workspace">
                <section class="editor" aria-label="Consent form setup">
                    if !*started {
                        <Intro on_start={{
                            let started = started.clone();
                            Callback::from(move |_| started.set(true))
                        }}
                        blank={*blank}
                        on_blank={{
                            let blank = blank.clone();
                            Callback::from(move |value: bool| blank.set(value))
                        }} />
                    } else if let Some(therapy) = therapy {
                        <TreatmentBlock
                            therapy={therapy}
                            catalogue={catalogue.clone()}
                            site={state.site.clone()}
                            template_id={template_id.clone()}
                            dispatch={dispatch.clone()}
                        />

                        <SearchPanel
                            catalogue={catalogue.clone()}
                            query={(*query).clone()}
                            on_query={{
                                let query = query.clone();
                                Callback::from(move |value: String| query.set(value))
                            }}
                            on_open={{
                                let dispatch = dispatch.clone();
                                let query = query.clone();
                                Callback::from(move |action: Action| {
                                    dispatch.emit(action);
                                    query.set(String::new());
                                })
                            }}
                        />

                        if *loading {
                            <section class="panel">
                                <p class="hint">{"Loading the form…"}</p>
                            </section>
                        }
                        if let Some(message) = (*error).clone() {
                            <section class="panel">
                                <p class="notice" role="alert">{message}</p>
                            </section>
                        }

                        if let Some(form) = form.as_deref() {
                            <SideEffectsBlock
                                form={form.data.clone()}
                                reviewed={state.reviewed.clone()}
                                other_notes={state.other_notes.clone()}
                                dispatch={dispatch.clone()}
                            />
                            <DeclarationsBlock
                                statements={form.data.statements.clone()}
                                declared={state.declared.clone()}
                                dispatch={dispatch.clone()}
                            />
                            <PrintBlock
                                summary={summary.clone()}
                                side_effects_total={form.data.side_effect_count()}
                                reviewed={state.reviewed.len()}
                                declared={state.declared.len()}
                                statements={form.data.statements.len()}
                                notice={(*notice).clone()}
                                on_print={on_print.clone()}
                                on_download={on_download.clone()}
                                enabled={true}
                                blank={*blank}
                                on_blank={{
                                    let blank = blank.clone();
                                    Callback::from(move |value: bool| blank.set(value))
                                }}
                            />
                        } else if !*loading && error.is_none() {
                            <PrintBlock
                                summary={None}
                                side_effects_total={0}
                                reviewed={0}
                                declared={0}
                                statements={0}
                                notice={(*notice).clone()}
                                on_print={on_print.clone()}
                                on_download={on_download.clone()}
                                enabled={false}
                                blank={*blank}
                                on_blank={{
                                    let blank = blank.clone();
                                    Callback::from(move |value: bool| blank.set(value))
                                }}
                            />
                        }
                    } else {
                        <Landing catalogue={catalogue.clone()} dispatch={dispatch.clone()} />
                    }
                </section>
            </main>
            <p class="print-only">
                {"This page prints nothing. Use 'Print both copies' and print from the PDF viewer."}
            </p>
            <p class="build-note">{format!("build {}", crate::BUILD)}</p>
        </div>
    }
}

#[derive(Properties, PartialEq)]
struct IntroProps {
    on_start: Callback<MouseEvent>,
    blank: bool,
    on_blank: Callback<bool>,
}

/// What the page is for, said plainly, before any form is chosen.
#[component]
fn Intro(props: &IntroProps) -> Html {
    html! {
        <div class="intro">
            <h1 class="landing-title">{"Consent forms, filled in on screen"}</h1>
            <p class="landing-sub">
                {"Choose the regimen, tick what you discussed with the patient, and print two
                  copies — one for the notes and one for the patient. It takes a few minutes
                  instead of hunting for the right paper form."}
            </p>

            <ol class="intro-steps">
                <li>
                    <span class="intro-step-title">{"Choose the regimen"}</span>
                    <span class="intro-step-text">
                        {"The side effects come straight from the national Cancer Research UK form
                          for that regimen, so the wording is the form's own."}
                    </span>
                </li>
                <li>
                    <span class="intro-step-title">{"Tick what you discussed"}</span>
                    <span class="intro-step-text">
                        {"Tick the side effects and the health professional statements. Use
                          “Tick all” and clear the few that do not apply."}
                    </span>
                </li>
                <li>
                    <span class="intro-step-title">{"Print two copies"}</span>
                    <span class="intro-step-text">
                        {"One file copy and one patient copy, already stamped. Write the patient's
                          details and signature by hand, then give them their copy."}
                    </span>
                </li>
            </ol>

            <p class="intro-privacy">
                <strong>{"No confidential details are collected."}</strong>
                {" Name, date of birth, NHS number and signature are left blank on purpose and
                  written by hand after printing. Nothing about the patient is typed into this
                  app, and nothing is stored or sent anywhere."}
            </p>

            <button type="button" class="btn btn-primary btn-large" onclick={props.on_start.clone()}>
                {"Choose a consent form"}
            </button>

            <label class="blank-toggle">
                <input
                    type="checkbox"
                    checked={props.blank}
                    onchange={{
                        let on_blank = props.on_blank.clone();
                        Callback::from(move |event: Event| {
                            let checked = event
                                .target_dyn_into::<web_sys::HtmlInputElement>()
                                .map(|input| input.checked())
                                .unwrap_or(false);
                            on_blank.emit(checked);
                        })
                    }}
                />
                <span>
                    <strong>{"Print blank forms"}</strong>
                    {" — leave every box empty so the form can be completed by hand."}
                </span>
            </label>
        </div>
    }
}

#[derive(Properties, PartialEq)]
struct HeaderProps {
    on_print: Callback<MouseEvent>,
    on_purge: Callback<MouseEvent>,
    purge_armed: bool,
    can_print: bool,
}

#[component]
fn Header(props: &HeaderProps) -> Html {
    html! {
        <header class="topbar">
            <div class="brand">
                <span class="brand-mark" aria-hidden="true"></span>
                <span class="brand-name">{"Consent"}</span>
                <span class="brand-sub">{"form builder"}</span>
            </div>

            <p class="privacy">
                <span class="privacy-dot" aria-hidden="true"></span>
                {"Runs entirely on this device · no patient details are entered or stored"}
            </p>

            <div class="topbar-actions">
                <button
                    type="button"
                    class={classes!("btn", "btn-ghost", props.purge_armed.then_some("btn-warn"))}
                    onclick={props.on_purge.clone()}
                >
                    {if props.purge_armed { "Clear everything?" } else { "Clear" }}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    onclick={props.on_print.clone()}
                    disabled={!props.can_print}
                >
                    {"Print both copies"}
                </button>
            </div>
        </header>
    }
}

#[derive(Properties, PartialEq)]
struct LandingProps {
    catalogue: Rc<Catalogue>,
    dispatch: Callback<Action>,
}

#[component]
fn Landing(props: &LandingProps) -> Html {
    let choice = |therapy: TherapyType, letter: &str| {
        let dispatch = props.dispatch.clone();
        let forms = props
            .catalogue
            .forms
            .iter()
            .filter(|form| form.therapy.unwrap_or(TherapyType::Sact) == therapy)
            .count();
        let onclick = Callback::from(move |_| dispatch.emit(Action::ChooseTherapy(therapy)));
        html! {
            <button type="button" class="choice" {onclick}>
                <span class="choice-letter">{letter}</span>
                <span class="choice-body">
                    <span class="choice-title">{therapy.label()}</span>
                    <span class="choice-note">{therapy.attribution()}</span>
                </span>
                <span class="choice-count">{format!("{forms} regimens")}</span>
            </button>
        }
    };

    html! {
        <div class="landing">
            <h1 class="landing-title">{"Which consent are you taking?"}</h1>
            <p class="landing-sub">{"Side effects load from the national form for the regimen."}</p>
            <div class="choices">
                {choice(TherapyType::Sact, "A")}
                {choice(TherapyType::Radiotherapy, "B")}
            </div>
        </div>
    }
}

#[derive(Properties, PartialEq)]
struct TreatmentBlockProps {
    therapy: TherapyType,
    catalogue: Rc<Catalogue>,
    site: Option<String>,
    template_id: Option<String>,
    dispatch: Callback<Action>,
}

#[component]
fn TreatmentBlock(props: &TreatmentBlockProps) -> Html {
    let sites = props.catalogue.sites(props.therapy);
    let regimens = props
        .site
        .as_deref()
        .map(|site| props.catalogue.regimens(props.therapy, site))
        .unwrap_or_default();

    let on_site = {
        let dispatch = props.dispatch.clone();
        Callback::from(move |event: Event| {
            let value = select_value(&event);
            if !value.is_empty() {
                dispatch.emit(Action::ChooseSite(value));
            }
        })
    };

    let on_regimen = {
        let dispatch = props.dispatch.clone();
        Callback::from(move |event: Event| {
            let value = select_value(&event);
            if !value.is_empty() {
                dispatch.emit(Action::ChooseRegimen(value));
            }
        })
    };

    html! {
        <section class="panel">
            <div class="panel-head">
                <h2 class="panel-title">{"Treatment"}</h2>
                <span class="tally">
                    {format!("{} regimens", props.catalogue.forms.len())}
                </span>
            </div>

            <div class="fields">
                <label class="field">
                    <span class="field-label">{"Tumour site"}</span>
                    <select class="control" onchange={on_site}>
                        <option value="" selected={props.site.is_none()}>{"Choose a site"}</option>
                        for site in &sites {
                            <option value={site.to_string()} selected={props.site.as_deref() == Some(*site)}>
                                {*site}
                            </option>
                        }
                    </select>
                </label>

                <label class="field">
                    <span class="field-label">{"Regimen"}</span>
                    <select class="control" onchange={on_regimen} disabled={regimens.is_empty()}>
                        <option value="" selected={props.template_id.is_none()}>
                            {if regimens.is_empty() {
                                "Choose a site first"
                            } else {
                                "Choose a regimen"
                            }}
                        </option>
                        for form in &regimens {
                            <option
                                value={form.id.clone()}
                                selected={props.template_id.as_deref() == Some(form.id.as_str())}
                            >
                                {form.regimen_name.clone()}
                            </option>
                        }
                    </select>
                </label>
            </div>
        </section>
    }
}

#[derive(Properties, PartialEq)]
struct SearchPanelProps {
    catalogue: Rc<Catalogue>,
    query: String,
    on_query: Callback<String>,
    on_open: Callback<Action>,
}

/// Keyword search across the catalogue, showing where each regimen is filed.
#[component]
fn SearchPanel(props: &SearchPanelProps) -> Html {
    let on_input = {
        let on_query = props.on_query.clone();
        Callback::from(move |event: InputEvent| {
            let value = event
                .target_dyn_into::<web_sys::HtmlInputElement>()
                .map(|input| input.value())
                .unwrap_or_default();
            on_query.emit(value);
        })
    };

    let needle = props.query.trim().to_lowercase();
    let tokens: Vec<&str> = needle.split_whitespace().collect();
    let matches: Vec<&crate::data::Summary> = if tokens.is_empty() {
        Vec::new()
    } else {
        props
            .catalogue
            .forms
            .iter()
            .filter(|form| {
                let haystack = format!(
                    "{} {}",
                    form.regimen_name.to_lowercase(),
                    form.tumour_site.to_lowercase()
                );
                tokens.iter().all(|token| haystack.contains(token))
            })
            .collect()
    };

    html! {
        <section class="panel">
            <div class="panel-head">
                <h2 class="panel-title">{"Search"}</h2>
                if !tokens.is_empty() {
                    <span class="tally">{format!("{} match{}", matches.len(), if matches.len() == 1 { "" } else { "es" })}</span>
                }
            </div>

            <label class="field field-wide">
                <span class="field-label">{"Drug or regimen"}</span>
                <input
                    class="control search-input"
                    type="search"
                    placeholder="e.g. capecitabine, FEC, pembrolizumab"
                    value={props.query.clone()}
                    oninput={on_input}
                    autocomplete="off"
                />
            </label>

            if !tokens.is_empty() {
                if matches.is_empty() {
                    <p class="hint">{"No regimen matches that. Try a drug name, or a tumour site such as “breast”."}</p>
                } else {
                    <ul class="search-results">
                        for form in matches.iter().take(40) {
                            <li key={form.id.clone()}>
                                <button
                                    type="button"
                                    class="search-row"
                                    onclick={{
                                        let on_open = props.on_open.clone();
                                        let site = form.tumour_site.clone();
                                        let id = form.id.clone();
                                        Callback::from(move |_| on_open.emit(Action::OpenForm {
                                            site: site.clone(),
                                            template_id: id.clone(),
                                        }))
                                    }}
                                >
                                    <span class="search-name">{form.regimen_name.clone()}</span>
                                    <span class="search-site">{format!("filed under {}", form.tumour_site)}</span>
                                </button>
                            </li>
                        }
                    </ul>
                    if matches.len() > 40 {
                        <p class="hint">{format!("Showing the first 40 of {} matches — add another word to narrow it.", matches.len())}</p>
                    }
                }
            }
        </section>
    }
}

#[derive(Properties, PartialEq)]
struct SideEffectsBlockProps {
    form: FormData,
    reviewed: std::collections::BTreeSet<usize>,
    other_notes: String,
    dispatch: Callback<Action>,
}

#[component]
fn SideEffectsBlock(props: &SideEffectsBlockProps) -> Html {
    let total = props.form.side_effect_count();
    let all_ticked = total > 0 && props.reviewed.len() >= total;

    let on_other_notes = {
        let dispatch = props.dispatch.clone();
        Callback::from(move |event: InputEvent| {
            dispatch.emit(Action::SetOtherNotes(textarea_value(&event)));
        })
    };

    html! {
        <section class="panel">
            <div class="panel-head">
                <h2 class="panel-title">{"Side effects discussed"}</h2>
                <span class="tally">
                    <strong>{props.reviewed.len()}</strong>
                    <span>{format!(" of {total} ticked")}</span>
                </span>
                <button
                    type="button"
                    class="btn btn-small"
                    aria-pressed={all_ticked.to_string()}
                    onclick={{
                        let dispatch = props.dispatch.clone();
                        Callback::from(move |_| {
                            dispatch.emit(Action::SetAllReviewed { total, ticked: !all_ticked })
                        })
                    }}
                >
                    {if all_ticked { "Clear all" } else { "Tick all" }}
                </button>
            </div>

            <SideEffectList
                groups={props.form.groups.clone()}
                reviewed={props.reviewed.clone()}
                dispatch={props.dispatch.clone()}
            />

            <label class="field field-wide">
                <span class="field-label">
                    {if props.form.has_free_text() {
                        "Anything else discussed"
                    } else {
                        "This form has no free-text area — anything extra has to be written by hand"
                    }}
                </span>
                if props.form.has_free_text() {
                    <textarea
                        class="control control-area"
                        rows="3"
                        placeholder="Other risks, questions raised, local services…"
                        value={props.other_notes.clone()}
                        oninput={on_other_notes}
                    />
                }
            </label>
        </section>
    }
}

#[derive(Properties, PartialEq)]
struct DeclarationsBlockProps {
    statements: Vec<Statement>,
    declared: std::collections::BTreeSet<usize>,
    dispatch: Callback<Action>,
}

#[component]
fn DeclarationsBlock(props: &DeclarationsBlockProps) -> Html {
    if props.statements.is_empty() {
        return html! {};
    }

    html! {
        <section class="panel">
            <div class="panel-head">
                <h2 class="panel-title">{"Health professional statement"}</h2>
                <span class="tally">
                    <strong>{props.declared.len()}</strong>
                    <span>{format!(" of {} confirmed", props.statements.len())}</span>
                </span>
            </div>
            <ul class="check-list">
                for statement in &props.statements {
                    <DeclarationRow
                        key={statement.index}
                        index={statement.index}
                        text={statement.text.clone()}
                        checked={props.declared.contains(&statement.index)}
                        dispatch={props.dispatch.clone()}
                    />
                }
            </ul>
        </section>
    }
}

#[derive(Properties, PartialEq)]
struct DeclarationRowProps {
    index: usize,
    text: String,
    checked: bool,
    dispatch: Callback<Action>,
}

#[component]
fn DeclarationRow(props: &DeclarationRowProps) -> Html {
    let id = format!("declaration-{}", props.index);
    let on_toggle = {
        let dispatch = props.dispatch.clone();
        let index = props.index;
        Callback::from(move |_| dispatch.emit(Action::ToggleDeclaration(index)))
    };

    html! {
        <li class={classes!("row", props.checked.then_some("is-checked"))}>
            <div class="row-main">
                <input
                    type="checkbox"
                    class="row-check"
                    id={id.clone()}
                    checked={props.checked}
                    onchange={on_toggle}
                />
                <label class="row-text" for={id}>{props.text.clone()}</label>
            </div>
        </li>
    }
}

#[derive(Properties, PartialEq)]
struct PrintBlockProps {
    summary: Option<crate::data::Summary>,
    side_effects_total: usize,
    reviewed: usize,
    declared: usize,
    statements: usize,
    notice: Option<String>,
    on_print: Callback<MouseEvent>,
    on_download: Callback<MouseEvent>,
    enabled: bool,
    blank: bool,
    on_blank: Callback<bool>,
}

#[component]
fn PrintBlock(props: &PrintBlockProps) -> Html {
    html! {
        <section class="panel">
            <div class="panel-head">
                <h2 class="panel-title">{"Print and complete"}</h2>
            </div>
            <p class="hint">
                {"Patient details and the signature are left blank on purpose — they are completed
                  by hand on the printed copy."}
            </p>
            if let Some(message) = &props.notice {
                <p class="notice" role="status">{message.clone()}</p>
            }
            <label class="blank-toggle">
                <input
                    type="checkbox"
                    checked={props.blank}
                    onchange={{
                        let on_blank = props.on_blank.clone();
                        Callback::from(move |event: Event| {
                            let checked = event
                                .target_dyn_into::<web_sys::HtmlInputElement>()
                                .map(|input| input.checked())
                                .unwrap_or(false);
                            on_blank.emit(checked);
                        })
                    }}
                    disabled={!props.enabled}
                />
                <span>
                    <strong>{"Blank form"}</strong>
                    {" — print it with every box empty to complete by hand."}
                </span>
            </label>
            <div class="panel-foot">
                <p class="foot-note">
                    {match &props.summary {
                        Some(form) => format!(
                            "{} · {} of {} side effects ticked · {} of {} declarations confirmed",
                            form.regimen_name,
                            props.reviewed,
                            props.side_effects_total,
                            props.declared,
                            props.statements,
                        ),
                        None => "Choose a regimen to begin.".to_owned(),
                    }}
                </p>
                <div class="foot-actions">
                    <button
                        type="button"
                        class="btn btn-primary btn-large"
                        onclick={props.on_print.clone()}
                        disabled={!props.enabled}
                    >
                        {if props.blank {
                            "Print blank copies — no ticks"
                        } else {
                            "Print both copies"
                        }}
                    </button>
                </div>
                <p class="foot-secondary">
                    <button
                        type="button"
                        class="link-button"
                        onclick={props.on_download.clone()}
                        disabled={!props.enabled}
                    >
                        {"Save a copy to this computer instead"}
                    </button>
                </p>
            </div>
        </section>
    }
}
