//! Writing the clinician's ticks into the official consent form.
//!
//! The form's PDF and its coordinate file are fetched at runtime, so nothing is compiled in
//! and the library can hold every CRUK regimen.
//!
//! Only ticks and free text are written. Patient details and the signature are left blank
//! on purpose, to be completed by hand on the printed form.

use std::collections::BTreeMap;

use lopdf::content::{Content, Operation};
use lopdf::{dictionary, Dictionary, Document, Object, ObjectId, StringFormat};

use crate::forms::FormData;
use crate::model::AppState;
use crate::pdf::{encode_win_ansi, wrap};

enum Mark {
    Text {
        x: f32,
        y: f32,
        size: f32,
        text: String,
    },
    Tick {
        x: f32,
        y: f32,
        in_box: bool,
    },
}

/// Fill the form: ticks and free text only.
///
/// # Errors
///
/// Returns a message when the PDF cannot be parsed or a tick points at a missing page.
pub fn fill(original: &[u8], form: &FormData, state: &AppState) -> Result<Vec<u8>, String> {
    let mut doc =
        Document::load_mem(original).map_err(|error| format!("cannot read form: {error}"))?;
    let pages = doc.get_pages();
    let mut marks: BTreeMap<u32, Vec<Mark>> = BTreeMap::new();

    for item in &form.side_effects {
        if !state.reviewed.contains(&item.index) {
            continue;
        }
        let (x, y, in_box) = form.tick_position(item);
        marks
            .entry(item.page)
            .or_default()
            .push(Mark::Tick { x, y, in_box });
    }

    for statement in &form.statements {
        if !state.declared.contains(&statement.index) {
            continue;
        }
        marks.entry(statement.page).or_default().push(Mark::Tick {
            x: statement.x,
            y: statement.y,
            in_box: true,
        });
    }

    if !state.other_notes.trim().is_empty() {
        if let Some(area) = form.free_text.as_ref() {
            let mut baseline = area.y;
            for line in wrap(&state.other_notes, 7.6, area.width) {
                marks.entry(area.page).or_default().push(Mark::Text {
                    x: area.x + 2.0,
                    y: baseline,
                    size: 7.6,
                    text: line,
                });
                baseline -= 9.0;
            }
        }
    }

    if marks.is_empty() {
        return Ok(original.to_vec());
    }

    let font_id = doc.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
        "Encoding" => "WinAnsiEncoding",
    });

    for page_number in marks.keys() {
        let Some(page_id) = pages.get(page_number).copied() else {
            return Err(format!("coordinate file refers to page {page_number}"));
        };
        ensure_font(&mut doc, page_id, font_id)?;
    }

    for (page_number, page_marks) in &marks {
        let Some(page_id) = pages.get(page_number).copied() else {
            continue;
        };
        let content = Content {
            operations: operations_for(page_marks, open_states(&doc, page_id)),
        };
        doc.add_to_page_content(page_id, content)
            .map_err(|error| format!("cannot write to page {page_number}: {error}"))?;
    }

    let mut out = Vec::new();
    doc.save_to(&mut out)
        .map_err(|error| format!("cannot serialise the form: {error}"))?;
    Ok(out)
}

/// Duplicate every page, stamping the second set with a patient-copy box.
///
/// Printing the result gives the form twice: one file copy, one patient copy.
///
/// # Errors
///
/// Returns a message when the document cannot be parsed or its page tree is unusual.
pub fn with_patient_copy(source: &[u8]) -> Result<Vec<u8>, String> {
    let mut doc =
        Document::load_mem(source).map_err(|error| format!("cannot read form: {error}"))?;
    let pages: Vec<ObjectId> = doc.get_pages().values().copied().collect();
    if pages.is_empty() {
        return Err("the form has no pages".to_owned());
    }

    let pages_root = doc
        .get_object(pages[0])
        .map_err(|error| format!("cannot read page 1: {error}"))?
        .as_dict()
        .map_err(|error| format!("page 1 is not a dictionary: {error}"))?
        .get(b"Parent")
        .ok()
        .and_then(|parent| parent.as_reference().ok())
        .ok_or_else(|| "page tree has no parent".to_owned())?;

    let font_id = doc.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica-Bold",
        "Encoding" => "WinAnsiEncoding",
    });

    let mut copies: Vec<ObjectId> = Vec::with_capacity(pages.len());
    for page_id in &pages {
        let mut page_dict = doc
            .get_object(*page_id)
            .map_err(|error| format!("cannot read a page: {error}"))?
            .as_dict()
            .map_err(|error| format!("page is not a dictionary: {error}"))?
            .clone();

        let width = media_dimension(&page_dict, 2, 595.28);
        let height = media_dimension(&page_dict, 3, 841.89);

        let banner_id = doc.add_object(banner_stream(width, height));
        let mut contents: Vec<Object> = match page_dict.get(b"Contents") {
            Ok(Object::Reference(id)) => vec![Object::Reference(*id)],
            Ok(Object::Array(items)) => items.clone(),
            _ => Vec::new(),
        };
        contents.push(Object::Reference(banner_id));
        page_dict.set("Contents", Object::Array(contents));
        page_dict.set("Parent", Object::Reference(pages_root));

        let copy_id = doc.add_object(Object::Dictionary(page_dict));
        ensure_font(&mut doc, copy_id, font_id)?;
        copies.push(copy_id);
    }

    let mut kids: Vec<Object> = pages.iter().map(|id| Object::Reference(*id)).collect();
    kids.extend(copies.iter().map(|id| Object::Reference(*id)));

    let total = kids.len() as i64;
    let pages_dict = doc
        .get_object_mut(pages_root)
        .map_err(|error| format!("cannot read the page tree: {error}"))?
        .as_dict_mut()
        .map_err(|error| format!("page tree is not a dictionary: {error}"))?;
    pages_dict.set("Kids", Object::Array(kids));
    pages_dict.set("Count", Object::Integer(total));

    let mut out = Vec::new();
    doc.save_to(&mut out)
        .map_err(|error| format!("cannot serialise the form: {error}"))?;
    Ok(out)
}

fn media_dimension(page_dict: &Dictionary, index: usize, fallback: f32) -> f32 {
    page_dict
        .get(b"MediaBox")
        .ok()
        .and_then(|object| object.as_array().ok())
        .and_then(|values| values.get(index))
        .and_then(|value| {
            value
                .as_float()
                .ok()
                .or_else(|| value.as_i64().ok().map(|number| number as f32))
        })
        .unwrap_or(fallback)
}

/// An outlined box across the top of the page reading PATIENT COPY.
///
/// Outline only: a filled band would use a lot of toner on every patient copy.
fn banner_stream(width: f32, height: f32) -> lopdf::Stream {
    let box_height = 20.0;
    let box_bottom = height - box_height - 10.0;
    let label = "PATIENT COPY - FOR YOUR REFERENCE";
    let size = 11.0;
    let text_width: f32 = label
        .chars()
        .map(|character| crate::pdf::text_width(&character.to_string(), size))
        .sum();
    let x = ((width - text_width) / 2.0).max(16.0);

    let mut content = Vec::new();
    content.extend_from_slice(
        format!(
            "q\n0 g\n0.8 w\n16 {box_bottom:.2} {box_width:.2} {box_height:.2} re S\nQ\n\
             q\n0 g\nBT\n/Fapp {size:.2} Tf\n1 0 0 1 {x:.2} {:.2} Tm\n({label}) Tj\nET\nQ\n",
            box_bottom + 6.0,
            box_width = width - 32.0,
        )
        .as_bytes(),
    );

    lopdf::Stream::new(dictionary! {}, content)
}

fn ensure_font(doc: &mut Document, page_id: ObjectId, font_id: ObjectId) -> Result<(), String> {
    let mut resources = {
        let page = doc
            .get_object(page_id)
            .map_err(|error| format!("cannot read the page: {error}"))?;
        let page_dict = page
            .as_dict()
            .map_err(|error| format!("page is not a dictionary: {error}"))?;
        match page_dict.get(b"Resources") {
            Ok(Object::Reference(id)) => doc
                .get_object(*id)
                .map_err(|error| format!("cannot read page resources: {error}"))?
                .as_dict()
                .map_err(|error| format!("page resources are not a dictionary: {error}"))?
                .clone(),
            Ok(Object::Dictionary(dict)) => dict.clone(),
            _ => Dictionary::new(),
        }
    };

    let mut fonts = match resources.get(b"Font") {
        Ok(Object::Reference(id)) => doc
            .get_object(*id)
            .map_err(|error| format!("cannot read the font dictionary: {error}"))?
            .as_dict()
            .map_err(|error| format!("font dictionary is not a dictionary: {error}"))?
            .clone(),
        Ok(Object::Dictionary(dict)) => dict.clone(),
        _ => Dictionary::new(),
    };

    fonts.set("Fapp", Object::Reference(font_id));
    resources.set("Font", Object::Dictionary(fonts));

    let page = doc
        .get_object_mut(page_id)
        .map_err(|error| format!("cannot open the page: {error}"))?;
    let page_dict = page
        .as_dict_mut()
        .map_err(|error| format!("page is not a dictionary: {error}"))?;
    page_dict.set("Resources", Object::Dictionary(resources));
    Ok(())
}

/// How many graphics states a page leaves open (`q` minus `Q` in its existing content).
///
/// Appending drawing to a page that has left a clip open would hide it, so those states are
/// popped first — but only the ones that are really open, because popping an empty stack is an
/// error that a strict reader may answer by ignoring everything that follows.
fn open_states(doc: &Document, page_id: ObjectId) -> usize {
    let Ok(page) = doc.get_object(page_id).and_then(|object| object.as_dict()) else {
        return 0;
    };
    let contents: Vec<ObjectId> = match page.get(b"Contents") {
        Ok(Object::Reference(id)) => vec![*id],
        Ok(Object::Array(items)) => items
            .iter()
            .filter_map(|item| item.as_reference().ok())
            .collect(),
        _ => Vec::new(),
    };

    let mut opens = 0usize;
    let mut closes = 0usize;
    for id in contents {
        let Ok(stream) = doc.get_object(id).and_then(|object| object.as_stream()) else {
            continue;
        };
        let Ok(data) = stream.decompressed_content() else {
            continue;
        };
        for token in data.split(|byte| byte.is_ascii_whitespace()) {
            match token {
                b"q" => opens += 1,
                b"Q" => closes += 1,
                _ => {}
            }
        }
    }
    opens.saturating_sub(closes)
}

fn operations_for(marks: &[Mark], open_states: usize) -> Vec<Operation> {
    let mut operations: Vec<Operation> = (0..open_states)
        .map(|_| Operation::new("Q", vec![]))
        .collect();
    operations.push(Operation::new("q", vec![]));
    // Ticks are stroked paths, so the stroke colour matters; `g` alone only sets the fill and
    // an inherited pale stroke colour would leave the tick invisible.
    operations.push(Operation::new("g", vec![Object::Real(0.0)]));
    operations.push(Operation::new("G", vec![Object::Real(0.0)]));

    for mark in marks {
        match mark {
            Mark::Text {
                x,
                y,
                size,
                text,
            } => {
                operations.push(Operation::new("BT", vec![]));
                operations.push(Operation::new(
                    "Tf",
                    vec![Object::Name(b"Fapp".to_vec()), Object::Real(*size)],
                ));
                operations.push(Operation::new(
                    "Tm",
                    vec![
                        1.into(),
                        0.into(),
                        0.into(),
                        1.into(),
                        Object::Real(*x),
                        Object::Real(*y),
                    ],
                ));
                operations.push(Operation::new(
                    "Tj",
                    vec![Object::String(encode_win_ansi(text), StringFormat::Literal)],
                ));
                operations.push(Operation::new("ET", vec![]));
            }
            Mark::Tick { x, y, in_box } => {
                if *in_box {
                    operations.push(Operation::new("w", vec![Object::Real(1.1)]));
                    operations.push(Operation::new(
                        "m",
                        vec![Object::Real(x - 3.0), Object::Real(y - 0.6)],
                    ));
                    operations.push(Operation::new(
                        "l",
                        vec![Object::Real(x - 0.8), Object::Real(y - 3.2)],
                    ));
                    operations.push(Operation::new(
                        "l",
                        vec![Object::Real(x + 3.6), Object::Real(y + 3.4)],
                    ));
                    operations.push(Operation::new("S", vec![]));
                } else {
                    let left = *x;
                    let bottom = *y - 2.6;
                    operations.push(Operation::new("w", vec![Object::Real(1.2)]));
                    operations.push(Operation::new(
                        "m",
                        vec![Object::Real(left), Object::Real(bottom + 2.6)],
                    ));
                    operations.push(Operation::new(
                        "l",
                        vec![Object::Real(left + 2.6), Object::Real(bottom - 0.4)],
                    ));
                    operations.push(Operation::new(
                        "l",
                        vec![Object::Real(left + 8.0), Object::Real(bottom + 6.4)],
                    ));
                    operations.push(Operation::new("S", vec![]));
                }
            }
        }
    }

    operations.push(Operation::new("Q", vec![]));
    operations
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::forms::FormData;

    /// One form to test against, read from disk so the repository does not have to carry
    /// Cancer Research UK's PDF. Run `python tools/import_all.py` first; without it these
    /// tests skip rather than fail.
    fn sample() -> Option<(Vec<u8>, FormData)> {
        let pdf = std::fs::read("sources/pdf/sact-breast-ac-docetaxel.pdf").ok()?;
        let fields =
            std::fs::read_to_string("assets/form_fields/sact-breast-ac-docetaxel.json").ok()?;
        let data = serde_json::from_str(&fields).ok()?;
        Some((pdf, data))
    }

    fn state() -> AppState {
        let mut state = AppState::default();
        state.reviewed.insert(0);
        state.reviewed.insert(1);
        state.declared.insert(0);
        state
    }

    #[test]
    fn patient_copy_keeps_the_ticks() {
        let Some((form_pdf, data)) = sample() else {
            eprintln!("sample form not imported yet - skipping");
            return;
        };
        let filled = fill(&form_pdf, &data, &state()).expect("fill with ticks");
        assert_ne!(filled, form_pdf, "the filled form must differ from the original");

        let doubled = with_patient_copy(&filled).expect("patient copy");
        let blank_doubled = with_patient_copy(&form_pdf).expect("patient copy of the blank form");
        assert_ne!(
            doubled, blank_doubled,
            "the two-copy PDF must keep the ticks: it is currently identical to a blank copy"
        );
    }

    #[test]
    fn blank_form_is_the_printed_form_untouched() {
        let Some((form_pdf, data)) = sample() else {
            eprintln!("sample form not imported yet - skipping");
            return;
        };
        let blank = fill(&form_pdf, &data, &AppState::default()).expect("blank fill");
        assert_eq!(
            blank, form_pdf,
            "a blank print must be the original form, byte for byte"
        );
    }

    #[test]
    fn blank_print_still_produces_two_copies() {
        let Some((form_pdf, data)) = sample() else {
            eprintln!("sample form not imported yet - skipping");
            return;
        };
        let blank = fill(&form_pdf, &data, &AppState::default()).expect("blank fill");
        let two = with_patient_copy(&blank).expect("patient copy");

        let original = Document::load_mem(&form_pdf).expect("read original");
        let doubled = Document::load_mem(&two).expect("read doubled");
        assert_eq!(
            doubled.get_pages().len(),
            original.get_pages().len() * 2,
            "the blank print must still be a file copy plus a patient copy"
        );
    }

    #[test]
    #[ignore = "dev tool: writes target/proofs/*.pdf so every tick can be checked on screen"]
    fn write_all_proofs() {
        let forms_dir = std::path::Path::new("forms");
        let out_dir = std::path::Path::new("target/proofs");
        std::fs::create_dir_all(out_dir).expect("create proofs dir");

        let mut written = 0usize;
        let mut failed: Vec<String> = Vec::new();

        for entry in std::fs::read_dir(forms_dir).expect("read forms dir") {
            let path = entry.expect("dir entry").path();
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                continue;
            }
            let id = path
                .file_stem()
                .map(|value| value.to_string_lossy().to_string())
                .unwrap_or_default();
            let Ok(json) = std::fs::read_to_string(&path) else {
                continue;
            };
            let Ok(data) = serde_json::from_str::<FormData>(&json) else {
                failed.push(format!("{id}: unreadable bundle"));
                continue;
            };
            let Ok(pdf) = std::fs::read(forms_dir.join(format!("{id}.pdf"))) else {
                failed.push(format!("{id}: missing PDF"));
                continue;
            };

            let mut state = AppState::default();
            state.reviewed = (0..data.side_effect_count()).collect();
            state.declared = (0..data.statements.len()).collect();

            match fill(&pdf, &data, &state) {
                Ok(filled) => {
                    std::fs::write(out_dir.join(format!("{id}.pdf")), filled).expect("write proof");
                    written += 1;
                }
                Err(error) => failed.push(format!("{id}: {error}")),
            }
        }

        println!("proofs written: {written}");
        for problem in &failed {
            println!("FAILED {problem}");
        }
    }

    #[test]
    fn filling_keeps_the_page_count() {
        let Some((form_pdf, data)) = sample() else {
            eprintln!("sample form not imported yet - skipping");
            return;
        };
        let filled = fill(&form_pdf, &data, &state()).expect("fill");
        assert!(filled.starts_with(b"%PDF"));
        assert_eq!(
            Document::load_mem(&filled).expect("parse").get_pages().len(),
            Document::load_mem(&form_pdf).expect("parse").get_pages().len()
        );
    }

    #[test]
    fn nothing_ticked_changes_nothing() {
        let Some((form_pdf, data)) = sample() else {
            eprintln!("sample form not imported yet - skipping");
            return;
        };
        let filled = fill(&form_pdf, &data, &AppState::default()).expect("fill");
        assert_eq!(filled.len(), form_pdf.len());
    }

    #[test]
    fn patient_copy_doubles_the_pages_with_one_banner_each() {
        let Some((form_pdf, data)) = sample() else {
            eprintln!("sample form not imported yet - skipping");
            return;
        };
        let single = fill(&form_pdf, &data, &state()).expect("single");
        let dual = with_patient_copy(&single).expect("dual");
        let pages = Document::load_mem(&single).expect("parse").get_pages().len() as u32;
        let doc = Document::load_mem(&dual).expect("parse");
        assert_eq!(doc.get_pages().len() as u32, pages * 2);

        let first: Vec<u32> = (1..=pages).collect();
        let second: Vec<u32> = ((pages + 1)..=(pages * 2)).collect();
        assert!(!doc
            .extract_text(&first)
            .unwrap_or_default()
            .contains("PATIENT COPY"));
        assert!(
            doc.extract_text(&second)
                .unwrap_or_default()
                .matches("PATIENT COPY")
                .count() as u32
                >= pages
        );
    }
}
