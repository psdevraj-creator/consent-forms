//! Text measurement and encoding for writing into a PDF.
//!
//! Only what the overlay needs: Helvetica advance widths, greedy word wrapping, and a
//! conversion to WinAnsi bytes with PDF string-literal escaping.

/// Helvetica advance widths for ASCII 32..=126, in 1/1000 em.
const WIDTHS: [u16; 95] = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
];

fn char_width(character: char, size: f32) -> f32 {
    let code = character as u32;
    let em = if (32..=126).contains(&code) {
        f32::from(WIDTHS[code as usize - 32])
    } else {
        match character {
            '—' | '–' => 1000.0,
            '“' | '”' | '’' => 333.0,
            '·' => 278.0,
            '°' => 400.0,
            _ => 556.0,
        }
    };
    em * size / 1000.0
}

/// Width of a string in points, at the given font size.
#[must_use]
pub fn text_width(text: &str, size: f32) -> f32 {
    text.chars()
        .map(|character| char_width(character, size))
        .sum()
}

/// Break `text` into lines that fit `width`, on word boundaries where possible.
#[must_use]
pub fn wrap(text: &str, size: f32, width: f32) -> Vec<String> {
    let mut lines = Vec::new();
    let mut line = String::new();
    for word in text.split_whitespace() {
        let candidate_width = if line.is_empty() {
            text_width(word, size)
        } else {
            text_width(&line, size) + text_width(" ", size) + text_width(word, size)
        };
        if candidate_width <= width || line.is_empty() {
            if !line.is_empty() {
                line.push(' ');
            }
            line.push_str(word);
        } else {
            lines.push(std::mem::take(&mut line));
            line.push_str(word);
        }
    }
    if !line.is_empty() {
        lines.push(line);
    }
    if lines.is_empty() {
        lines.push(String::new());
    }
    lines
}

/// Map a character to its WinAnsi byte, falling back to `?`.
fn win_ansi(character: char) -> u8 {
    match character {
        '—' => 0x97,
        '–' => 0x96,
        '‘' => 0x91,
        '’' => 0x92,
        '“' => 0x93,
        '”' => 0x94,
        '•' => 0x95,
        '·' => 0xB7,
        '°' => 0xB0,
        '✓' => b'x',
        '\n' | '\r' | '\t' => b' ',
        _ if character.is_ascii() => character as u8,
        _ => b'?',
    }
}

/// Encode text as WinAnsi bytes, escaping what PDF string literals require.
#[must_use]
pub fn encode_win_ansi(text: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(text.len());
    for character in text.chars() {
        let byte = win_ansi(character);
        match byte {
            b'(' | b')' | b'\\' => {
                out.push(b'\\');
                out.push(byte);
            }
            0x20..=0x7E | 0x80..=0xFF => out.push(byte),
            _ => out.push(b'?'),
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wrapping_keeps_every_word() {
        let text = "Feeling sick (nausea), being sick (vomiting), sore mouth and ulcers, taste changes.";
        let lines = wrap(text, 9.0, 200.0);
        assert!(lines.len() > 1, "should need several lines");
        assert!(lines.iter().all(|line| text_width(line, 9.0) <= 200.0));
        assert_eq!(lines.join(" "), text);
    }

    #[test]
    fn wrapping_a_long_word_still_returns_a_line() {
        let lines = wrap("supercalifragilisticexpialidocious", 9.0, 40.0);
        assert_eq!(lines.len(), 1);
    }

    #[test]
    fn text_width_grows_with_size() {
        assert!(text_width("hello", 10.0) < text_width("hello", 20.0));
    }

    #[test]
    fn parentheses_and_backslashes_are_escaped() {
        assert_eq!(encode_win_ansi("AC (test) \\ ok"), b"AC \\(test\\) \\\\ ok".to_vec());
    }

    #[test]
    fn unicode_degrades_to_question_marks_but_keeps_winansi_punctuation() {
        let encoded = encode_win_ansi("37.5°C — 日本 · 50–100%");
        assert!(encoded.contains(&0x97), "em dash becomes a WinAnsi byte");
        assert!(encoded.contains(&0xB0), "degree sign becomes a WinAnsi byte");
        assert_eq!(encoded.iter().filter(|byte| **byte == b'?').count(), 2);
    }
}
