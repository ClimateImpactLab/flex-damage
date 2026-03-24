// FlexDamage Report Template for Typst
// Minimal functional template

#let article(
  title: none,
  subtitle: none,
  authors: none,
  date: none,
  body,
) = {
  set page(
    paper: "us-letter",
    margin: (top: 2.5cm, bottom: 2.5cm, left: 2.5cm, right: 2.5cm),
    numbering: "1",
  )
  set text(font: "Libertinus Serif", size: 11pt)
  set heading(numbering: "1.1")
  set par(justify: true)

  // Title block
  align(center)[
    #text(size: 18pt, weight: "bold")[#title]
    #v(0.5em)
    #if subtitle != none {
      text(size: 14pt, fill: gray)[#subtitle]
      v(0.5em)
    }
    #if authors != none {
      text(size: 12pt)[#authors.join(", ")]
      v(0.3em)
    }
    #if date != none {
      text(size: 10pt, fill: gray)[#date]
    }
    #v(2em)
  ]

  body
}
