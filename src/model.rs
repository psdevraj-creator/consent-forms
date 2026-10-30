//! Application state and the actions that change it.
//!
//! The state deliberately holds **no patient details and no signature**. Name, date of
//! birth, NHS number, consultant and signature are completed by hand on the printed form,
//! so the app never handles identifiable data at all.

use std::collections::BTreeSet;
use std::rc::Rc;

use crate::data::TherapyType;

/// Everything the screen needs to know.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct AppState {
    /// `None` means the landing screen is showing.
    pub therapy: Option<TherapyType>,
    pub site: Option<String>,
    pub template_id: Option<String>,
    /// Indexes into the selected form's `side_effects` that the clinician has ticked.
    pub reviewed: BTreeSet<usize>,
    /// Health professional declarations the clinician has confirmed, by statement index.
    pub declared: BTreeSet<usize>,
    /// Anything else discussed, recorded once per form.
    pub other_notes: String,
}

/// Every way the state can change.
#[derive(Clone, Debug, PartialEq)]
pub enum Action {
    ChooseTherapy(TherapyType),
    ChooseSite(String),
    ChooseRegimen(String),
    /// Pick a site and regimen together, used by the search results.
    OpenForm { site: String, template_id: String },
    ToggleSideEffect(usize),
    /// Tick or clear every side effect at once, for the "tick all, then untick" workflow.
    SetAllReviewed { total: usize, ticked: bool },
    ToggleDeclaration(usize),
    SetOtherNotes(String),
    Purge,
}

/// Reducer over `Rc<AppState>` so the state can be handed to child components cheaply.
pub fn reduce(state: &Rc<AppState>, action: Action) -> Rc<AppState> {
    let mut next = (**state).clone();
    match action {
        Action::ChooseTherapy(therapy) => {
            if next.therapy != Some(therapy) {
                next.therapy = Some(therapy);
                next.site = None;
                next.template_id = None;
                next.reviewed.clear();
                next.declared.clear();
            }
        }
        Action::ChooseSite(site) => {
            if next.site.as_deref() != Some(site.as_str()) {
                next.site = Some(site);
                next.template_id = None;
                next.reviewed.clear();
                next.declared.clear();
            }
        }
        Action::ChooseRegimen(id) => {
            if next.template_id.as_deref() != Some(id.as_str()) {
                next.template_id = Some(id);
                next.reviewed.clear();
                next.declared.clear();
            }
        }
        Action::OpenForm { site, template_id } => {
            next.site = Some(site);
            next.template_id = Some(template_id);
            next.reviewed.clear();
            next.declared.clear();
        }
        Action::ToggleSideEffect(index) => {
            if !next.reviewed.remove(&index) {
                next.reviewed.insert(index);
            }
        }
        Action::SetAllReviewed { total, ticked } => {
            if ticked {
                next.reviewed = (0..total).collect();
            } else {
                next.reviewed.clear();
            }
        }
        Action::ToggleDeclaration(index) => {
            if !next.declared.remove(&index) {
                next.declared.insert(index);
            }
        }
        Action::SetOtherNotes(text) => next.other_notes = text,
        Action::Purge => return Rc::new(AppState::default()),
    }
    Rc::new(next)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn state() -> Rc<AppState> {
        Rc::new(AppState::default())
    }

    #[test]
    fn choosing_a_therapy_pins_the_landing_choice() {
        let state = reduce(&state(), Action::ChooseTherapy(TherapyType::Sact));
        assert_eq!(state.therapy, Some(TherapyType::Sact));
    }

    #[test]
    fn switching_therapy_clears_downstream_selection() {
        let mut current = reduce(&state(), Action::ChooseTherapy(TherapyType::Sact));
        current = reduce(&current, Action::ChooseSite("Breast".into()));
        current = reduce(&current, Action::ChooseRegimen("sact-breast-ec".into()));
        current = reduce(&current, Action::ToggleSideEffect(0));
        assert_eq!(current.reviewed.len(), 1);

        let switched = reduce(&current, Action::ChooseTherapy(TherapyType::Radiotherapy));
        assert_eq!(switched.therapy, Some(TherapyType::Radiotherapy));
        assert!(switched.site.is_none());
        assert!(switched.template_id.is_none());
        assert!(switched.reviewed.is_empty());
    }

    #[test]
    fn changing_site_clears_the_regimen() {
        let mut current = reduce(&state(), Action::ChooseTherapy(TherapyType::Sact));
        current = reduce(&current, Action::ChooseSite("Breast".into()));
        current = reduce(&current, Action::ChooseRegimen("sact-breast-ec".into()));
        current = reduce(&current, Action::ToggleSideEffect(0));
        let moved = reduce(&current, Action::ChooseSite("Brain/CNS".into()));
        assert!(moved.template_id.is_none());
        assert!(moved.reviewed.is_empty());
    }

    #[test]
    fn toggling_a_side_effect_flips_it_both_ways() {
        let on = reduce(&state(), Action::ToggleSideEffect(3));
        assert!(on.reviewed.contains(&3));
        let off = reduce(&on, Action::ToggleSideEffect(3));
        assert!(!off.reviewed.contains(&3));
    }

    #[test]
    fn tick_all_sets_every_index_and_clear_all_removes_them() {
        let all = reduce(
            &state(),
            Action::SetAllReviewed {
                total: 29,
                ticked: true,
            },
        );
        assert_eq!(all.reviewed.len(), 29);
        assert!(all.reviewed.contains(&28));

        let none = reduce(&all, Action::SetAllReviewed { total: 29, ticked: false });
        assert!(none.reviewed.is_empty());
    }

    #[test]
    fn declarations_are_remembered_and_cleared_with_the_form() {
        let current = reduce(&state(), Action::ToggleDeclaration(0));
        assert!(current.declared.contains(&0));

        let mut chosen = reduce(&current, Action::ChooseTherapy(TherapyType::Sact));
        chosen = reduce(&chosen, Action::ChooseSite("Breast".into()));
        assert!(chosen.declared.is_empty(), "switching form clears declarations");
    }

    #[test]
    fn purge_clears_everything() {
        let mut current = reduce(&state(), Action::ChooseTherapy(TherapyType::Sact));
        current = reduce(&current, Action::ToggleSideEffect(0));
        let purged = reduce(&current, Action::Purge);
        assert!(purged.therapy.is_none());
        assert!(purged.reviewed.is_empty());
    }

    #[test]
    fn other_notes_are_kept_and_replaced() {
        let with = reduce(&state(), Action::SetOtherNotes("Large print requested".into()));
        assert_eq!(with.other_notes, "Large print requested");
        let replaced = reduce(&with, Action::SetOtherNotes("".into()));
        assert!(replaced.other_notes.is_empty());
    }
}
