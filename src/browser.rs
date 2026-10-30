//! Handing the filled PDF to the browser.

use wasm_bindgen::JsCast;
use web_sys::{Blob, BlobPropertyBag, HtmlAnchorElement, Url};

/// Build a PDF blob from bytes.
fn pdf_blob(bytes: &[u8]) -> Option<Blob> {
    let array = js_sys::Uint8Array::from(bytes);
    let parts = js_sys::Array::new();
    parts.push(&array);
    let options = BlobPropertyBag::new();
    options.set_type("application/pdf");
    Blob::new_with_u8_array_sequence_and_options(&parts, &options).ok()
}

/// Open the filled form in a new tab, where the browser's PDF viewer prints or saves it.
pub fn open_pdf(bytes: &[u8]) -> bool {
    let Some(window) = web_sys::window() else {
        return false;
    };
    let Some(blob) = pdf_blob(bytes) else {
        return false;
    };
    let Ok(href) = Url::create_object_url_with_blob(&blob) else {
        return false;
    };
    matches!(window.open_with_url_and_target(&href, "_blank"), Ok(Some(_)))
}

/// Save the filled form with the given file name.
pub fn save_pdf(bytes: &[u8], filename: &str) -> bool {
    let Some(window) = web_sys::window() else {
        return false;
    };
    let Some(document) = window.document() else {
        return false;
    };
    let Some(blob) = pdf_blob(bytes) else {
        return false;
    };
    let Ok(href) = Url::create_object_url_with_blob(&blob) else {
        return false;
    };
    let Ok(element) = document.create_element("a") else {
        return false;
    };
    let Ok(anchor) = element.dyn_into::<HtmlAnchorElement>() else {
        return false;
    };
    anchor.set_href(&href);
    anchor.set_download(filename);
    anchor.set_attribute("hidden", "").ok();

    let appended = document
        .body()
        .map(|body| body.append_child(anchor.as_ref()).is_ok())
        .unwrap_or(false);
    anchor.click();
    if appended {
        if let Some(body) = document.body() {
            let _ = body.remove_child(anchor.as_ref());
        }
    }
    Url::revoke_object_url(&href).ok();
    true
}
