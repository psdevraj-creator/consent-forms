//! Client-side consent form builder.
//!
//! The regimen catalogue is compiled in; each form's wording, tick coordinates and PDF are
//! fetched when it is selected. Everything else — ticking, declarations, printing — happens
//! in the browser, and no patient details are ever collected.

mod app;
mod browser;
mod components;
mod data;
mod document;
mod forms;
mod loader;
mod model;
mod overlay;
mod pdf;

/// Which build this page is running. Shown when something goes wrong so a report can say
/// exactly which version was in use.
pub const BUILD: &str = "2026-10-30c";

fn main() {
    let document = web_sys::window().and_then(|window| window.document());
    let Some(root) = document.and_then(|document| document.get_element_by_id("root")) else {
        web_sys::console::error_1(&"missing #root mount point".into());
        return;
    };
    yew::Renderer::<app::App>::with_root(root).render();
}
