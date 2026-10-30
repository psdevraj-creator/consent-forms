//! The embedded catalogue of consent forms.
//!
//! Only identifiers and labels are compiled in — the side-effect text, coordinates and the
//! PDF itself are fetched when a regimen is selected, which keeps the wasm small enough to
//! carry the whole CRUK library.

use serde::Deserialize;

/// Which national consent-form library a regimen comes from.
#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[serde(rename_all = "kebab-case")]
pub enum TherapyType {
    Sact,
    Radiotherapy,
}

impl TherapyType {
    pub const ALL: [Self; 2] = [Self::Sact, Self::Radiotherapy];

    /// Button label on the landing screen.
    #[must_use]
    pub fn label(self) -> &'static str {
        match self {
            Self::Sact => "Systemic Anti-Cancer Therapy (SACT)",
            Self::Radiotherapy => "Radiotherapy",
        }
    }

    /// Who publishes the forms, shown under the button.
    #[must_use]
    pub fn attribution(self) -> &'static str {
        match self {
            Self::Sact => "Cancer Research UK regimen-specific SACT consent forms",
            Self::Radiotherapy => "Royal College of Radiologists site-specific radiotherapy forms",
        }
    }
}

/// One entry in the catalogue.
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Summary {
    pub id: String,
    pub tumour_site: String,
    pub regimen_name: String,
    #[serde(default)]
    pub therapy: Option<TherapyType>,
}

/// The whole embedded catalogue.
#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Catalogue {
    pub version: String,
    pub forms: Vec<Summary>,
}

impl Catalogue {
    /// Load the catalogue compiled into the binary.
    ///
    /// # Errors
    ///
    /// Returns the `serde_json` error if the embedded JSON is malformed.
    pub fn embedded() -> Result<Self, serde_json::Error> {
        serde_json::from_str(include_str!("../assets/catalogue.json"))
    }

    /// The therapies actually present in this build.
    #[must_use]
    pub fn therapies(&self) -> Vec<TherapyType> {
        TherapyType::ALL
            .into_iter()
            .filter(|therapy| {
                self.forms
                    .iter()
                    .any(|form| form.therapy.unwrap_or(TherapyType::Sact) == *therapy)
            })
            .collect()
    }

    /// Every site for a therapy, in catalogue order, deduplicated.
    #[must_use]
    pub fn sites(&self, therapy: TherapyType) -> Vec<&str> {
        let mut seen = std::collections::BTreeSet::new();
        self.forms
            .iter()
            .filter(|form| form.therapy.unwrap_or(TherapyType::Sact) == therapy)
            .map(|form| form.tumour_site.as_str())
            .filter(|site| seen.insert(*site))
            .collect()
    }

    /// The regimens for one site, in catalogue order.
    #[must_use]
    pub fn regimens(&self, therapy: TherapyType, site: &str) -> Vec<&Summary> {
        self.forms
            .iter()
            .filter(|form| {
                form.therapy.unwrap_or(TherapyType::Sact) == therapy && form.tumour_site == site
            })
            .collect()
    }

    /// Look one form up by id.
    #[must_use]
    pub fn form(&self, id: &str) -> Option<&Summary> {
        self.forms.iter().find(|form| form.id == id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn catalogue() -> Catalogue {
        Catalogue::embedded().expect("embedded catalogue must parse")
    }

    #[test]
    fn catalogue_parses_and_has_forms() {
        let catalogue = catalogue();
        assert!(!catalogue.forms.is_empty());
        assert!(!catalogue.version.is_empty());
    }

    #[test]
    fn ids_are_unique_and_labels_present() {
        let catalogue = catalogue();
        let mut ids = std::collections::BTreeSet::new();
        for form in &catalogue.forms {
            assert!(ids.insert(form.id.clone()), "duplicate id {}", form.id);
            assert!(!form.regimen_name.trim().is_empty(), "{} has no name", form.id);
            assert!(!form.tumour_site.trim().is_empty(), "{} has no site", form.id);
        }
    }

    #[test]
    fn every_site_has_at_least_one_regimen() {
        let catalogue = catalogue();
        for therapy in catalogue.therapies() {
            for site in catalogue.sites(therapy) {
                assert!(
                    !catalogue.regimens(therapy, site).is_empty(),
                    "{site} has no regimens"
                );
            }
        }
    }
}
