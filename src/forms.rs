//! One consent form as fetched at runtime: its wording, its tick positions and its PDF.

use std::collections::BTreeMap;

use serde::Deserialize;

/// A heading and the side effects printed under it.
#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
pub struct Group {
    #[serde(default)]
    pub heading: String,
    #[serde(default)]
    pub items: Vec<String>,
}

/// A written position on the form, in PDF coordinates (origin bottom-left).
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct FieldPos {
    pub page: u32,
    pub x: f32,
    pub y: f32,
    #[serde(default)]
    pub size: f32,
    #[serde(default)]
    pub max_width: f32,
}

/// A box on the form.
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Rect {
    pub page: u32,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    #[serde(default)]
    pub height: f32,
}

/// The printed tick-box columns on a page, where the form has a grid.
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct BoxColumn {
    pub page: u32,
    #[serde(default)]
    pub xs: Vec<f32>,
}

/// Where one side effect's tick goes.
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct SideEffectTick {
    pub index: usize,
    pub page: u32,
    /// Baseline of the printed line, for a margin tick.
    pub y: f32,
    #[serde(default)]
    pub box_y: Option<f32>,
    #[serde(default)]
    pub box_x: Option<f32>,
    #[serde(default)]
    pub band: Option<u8>,
    #[serde(default)]
    pub text_x: f32,
    #[serde(default)]
    pub margin_x: Option<f32>,
}

/// A tickable statement printed on the form.
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Statement {
    pub index: usize,
    pub page: u32,
    pub x: f32,
    pub y: f32,
    #[serde(default)]
    pub text: String,
}

/// Everything the app needs about one form.
#[derive(Clone, Debug, Default, Deserialize, PartialEq)]
pub struct FormData {
    #[serde(default)]
    pub id: String,
    #[serde(default)]
    pub tumour_site: String,
    #[serde(default)]
    pub regimen_name: String,
    #[serde(default)]
    pub groups: Vec<Group>,
    #[serde(default)]
    pub fields: BTreeMap<String, FieldPos>,
    #[serde(default)]
    pub box_columns: Vec<BoxColumn>,
    #[serde(default)]
    pub side_effects: Vec<SideEffectTick>,
    #[serde(default)]
    pub statements: Vec<Statement>,
    #[serde(default)]
    pub signature: Option<Rect>,
    #[serde(default)]
    pub free_text: Option<Rect>,
}

impl FormData {
    /// Every side effect, flattened, in printed order.
    #[must_use]
    pub fn side_effect_count(&self) -> usize {
        self.groups.iter().map(|group| group.items.len()).sum()
    }

    /// True when the form has an area for free text.
    #[must_use]
    pub fn has_free_text(&self) -> bool {
        self.free_text.is_some()
    }

    /// The x centre of a printed tick box.
    #[must_use]
    pub fn box_x(&self, page: u32, band: u8) -> Option<f32> {
        self.box_columns
            .iter()
            .find(|column| column.page == page)
            .and_then(|column| column.xs.get(usize::from(band)).copied())
    }

    /// Where to draw a side effect's tick: inside the form's own checkbox when it has one.
    #[must_use]
    pub fn tick_position(&self, item: &SideEffectTick) -> (f32, f32, bool) {
        if let (Some(box_x), Some(box_y)) = (item.box_x, item.box_y) {
            return (box_x, box_y, true);
        }
        if let (Some(box_y), Some(band)) = (item.box_y, item.band) {
            if let Some(x) = self.box_x(item.page, band) {
                return (x, box_y, true);
            }
        }
        let x = item.margin_x.unwrap_or(item.text_x - 12.0);
        (x, item.y, false)
    }
}
