.pragma library

var wordJoiner = "\u2060"

function tokenEndingAt(tokens, cursorPosition, selectionStart, selectionEnd) {
  if (selectionStart !== selectionEnd)
    return null
  for (var index = tokens.length - 1; index >= 0; index--) {
    if (tokens[index].end === cursorPosition)
      return tokens[index]
  }
  return null
}

function withoutToken(tokens, tokenId) {
  return tokens.filter(function(token) { return token.id !== tokenId })
}

function literalizeKind(text, tokens, kind) {
  var matching = tokens
    .filter(function(token) { return token.kind === kind })
    .slice()
    .sort(function(left, right) { return right.start - left.start })
  var literal = text
  for (var index = 0; index < matching.length; index++) {
    var insertion = Math.min(matching[index].start + 1, literal.length)
    literal = literal.slice(0, insertion) + wordJoiner + literal.slice(insertion)
  }
  return literal
}

function cursorAfterLiteralizingKind(cursorPosition, tokens, kind) {
  var offset = 0
  for (var index = 0; index < tokens.length; index++) {
    if (tokens[index].kind === kind && tokens[index].start < cursorPosition)
      offset++
  }
  return cursorPosition + offset
}
