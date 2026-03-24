#show: article.with(
  title: "$title$",
  subtitle: "$subtitle$",
  authors: ($for(author)$"$author$",$endfor$),
  date: "$date$",
)
