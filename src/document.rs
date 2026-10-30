//! Turns the clinician's ticks into a PDF.

use crate::loader::Loaded;
use crate::model::AppState;
use crate::overlay;

/// The single copy, ticks in place.
///
/// # Errors
///
/// Returns a message when the PDF cannot be written.
pub fn build(loaded: &Loaded, state: &AppState) -> Result<Vec<u8>, String> {
    overlay::fill(&loaded.pdf, &loaded.data, state)
}

/// The form twice: file copy, then a stamped patient copy.
///
/// # Errors
///
/// Returns a message when the PDF cannot be written or duplicated.
pub fn build_with_patient_copy(loaded: &Loaded, state: &AppState) -> Result<Vec<u8>, String> {
    overlay::with_patient_copy(&build(loaded, state)?)
}

/// The form with nothing drawn on it, for a clinician who wants to fill it by hand.
///
/// # Errors
///
/// Returns a message when the PDF cannot be written.
pub fn build_blank(loaded: &Loaded) -> Result<Vec<u8>, String> {
    overlay::fill(&loaded.pdf, &loaded.data, &AppState::default())
}

/// The blank form twice: file copy, then a stamped patient copy.
///
/// # Errors
///
/// Returns a message when the PDF cannot be written or duplicated.
pub fn build_blank_with_patient_copy(loaded: &Loaded) -> Result<Vec<u8>, String> {
    overlay::with_patient_copy(&build_blank(loaded)?)
}
