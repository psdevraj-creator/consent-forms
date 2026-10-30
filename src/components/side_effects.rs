//! The tick list: every side effect of the selected form, under its printed heading.

use std::collections::BTreeSet;

use yew::prelude::*;

use crate::forms::Group;
use crate::model::Action;

#[derive(Properties, PartialEq)]
pub struct SideEffectListProps {
    pub groups: Vec<Group>,
    pub reviewed: BTreeSet<usize>,
    pub dispatch: Callback<Action>,
}

#[component]
pub fn SideEffectList(props: &SideEffectListProps) -> Html {
    // Number the items once, in printed order, so the tick indexes match the coordinate file.
    let mut cursor = 0usize;
    let numbered: Vec<(String, Vec<(usize, String)>)> = props
        .groups
        .iter()
        .map(|group| {
            let items = group
                .items
                .iter()
                .map(|item| {
                    let index = cursor;
                    cursor += 1;
                    (index, item.clone())
                })
                .collect();
            (group.heading.clone(), items)
        })
        .collect();

    html! {
        <div class="groups">
            for (heading, items) in numbered {
                <section class="group" key={heading.clone()}>
                    <h3 class="group-title">{heading}</h3>
                    <ul class="check-list">
                        for (index, text) in items {
                            <SideEffectRow
                                key={index}
                                index={index}
                                text={text}
                                checked={props.reviewed.contains(&index)}
                                dispatch={props.dispatch.clone()}
                            />
                        }
                    </ul>
                </section>
            }
        </div>
    }
}

#[derive(Properties, PartialEq)]
struct SideEffectRowProps {
    index: usize,
    text: String,
    checked: bool,
    dispatch: Callback<Action>,
}

#[component]
fn SideEffectRow(props: &SideEffectRowProps) -> Html {
    let input_id = format!("side-effect-{}", props.index);

    let on_toggle = {
        let dispatch = props.dispatch.clone();
        let index = props.index;
        Callback::from(move |_| dispatch.emit(Action::ToggleSideEffect(index)))
    };

    html! {
        <li class={classes!("row", props.checked.then_some("is-checked"))}>
            <div class="row-main">
                <input
                    type="checkbox"
                    class="row-check"
                    id={input_id.clone()}
                    checked={props.checked}
                    onchange={on_toggle}
                />
                <label class="row-text" for={input_id}>{props.text.clone()}</label>
            </div>
        </li>
    }
}
