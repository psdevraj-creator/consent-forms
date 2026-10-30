//! Fetching a consent form from the site.

use gloo_net::http::Request;

use crate::forms::FormData;

/// A form's data plus its PDF.
#[derive(Clone, Debug, PartialEq)]
pub struct Loaded {
    pub data: FormData,
    pub pdf: Vec<u8>,
}

/// Fetch one form: `consent/forms/<id>.json` and `consent/forms/<id>.pdf`.
///
/// Paths are relative to the page, so the app works at the site root or in a subfolder.
///
/// # Errors
///
/// Returns a readable message when the request fails or the JSON is malformed.
pub async fn load(id: &str) -> Result<Loaded, String> {
    let json_url = format!("consent/forms/{id}.json");
    let pdf_url = format!("consent/forms/{id}.pdf");

    let response = Request::get(&json_url)
        .send()
        .await
        .map_err(|error| format!("could not reach {json_url}: {error}"))?;
    if !response.ok() {
        return Err(format!("{json_url} returned {}", response.status()));
    }
    let json = response
        .text()
        .await
        .map_err(|error| format!("{json_url} could not be read: {error}"))?;
    let data: FormData = serde_json::from_str(&json)
        .map_err(|error| format!("{json_url} is not valid form data: {error}"))?;

    let response = Request::get(&pdf_url)
        .send()
        .await
        .map_err(|error| format!("could not reach {pdf_url}: {error}"))?;
    if !response.ok() {
        return Err(format!("{pdf_url} returned {}", response.status()));
    }
    let pdf = response
        .binary()
        .await
        .map_err(|error| format!("{pdf_url} could not be read: {error}"))?;

    Ok(Loaded { data, pdf })
}
