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

// --- Account autocomplete -------------------------------------------------
//
// Todoist's Quick Add opens a picker the moment a sigil is typed. These functions decide, from the
// text and the cursor alone, whether a picker is open and what picking an entry rewrites.

var maxSuggestions = 8
var maxQueryLength = 40

var reminderChoices = [
  "5 min before", "10 min before", "30 min before", "1 hour before", "1 day before"
]

var priorityChoices = [
  { value: "p1", detail: "Urgent" },
  { value: "p2", detail: "High" },
  { value: "p3", detail: "Medium" },
  { value: "p4", detail: "None" }
]

function fold(text) {
  return String(text).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
}

function isSpace(character) {
  return character === undefined || /\s/.test(character)
}

// Text a mention of `name` is written as. Todoist reads a project, section or label name that
// contains spaces as written, so the name goes in unchanged.
function mention(sigil, name) {
  return sigil + name
}

// The project a `#mention` before `upto` refers to, or null. A name may contain spaces, so the
// longest known name that the text continues with wins.
function projectBefore(text, upto, account) {
  var projects = (account && account.projects) || []
  for (var i = upto - 1; i >= 0; i--) {
    if (text[i] !== "#" || !isSpace(text[i - 1]))
      continue
    var tail = fold(text.slice(i + 1, upto))
    var best = null
    for (var p = 0; p < projects.length; p++) {
      var name = fold(projects[p].name)
      if (!name || tail.indexOf(name) !== 0)
        continue
      var next = tail.charAt(name.length)
      if (next !== "" && !/\s/.test(next))
        continue
      if (!best || name.length > fold(best.name).length)
        best = projects[p]
    }
    if (best)
      return best
  }
  return null
}

function rank(name, query) {
  var folded = fold(name)
  if (query === "")
    return 3
  if (folded.indexOf(query) === 0)
    return 0
  if (folded.split(/[\s\-_]+/).some(function(word) { return word.indexOf(query) === 0 }))
    return 1
  return folded.indexOf(query) >= 0 ? 2 : -1
}

function pick(entries, query) {
  var ranked = []
  for (var i = 0; i < entries.length; i++) {
    var score = rank(entries[i].name, query)
    if (score >= 0)
      ranked.push({ entry: entries[i], score: score, order: i })
  }
  ranked.sort(function(a, b) { return a.score - b.score || a.order - b.order })
  return ranked.slice(0, maxSuggestions).map(function(item) { return item.entry })
}

function suggestionsFor(sigil, query, text, start, account) {
  var data = account || {}
  var entries = []
  var kind = ""
  if (sigil === "#") {
    kind = "project"
    entries = (data.projects || []).map(function(project) {
      var count = (data.sections || []).filter(function(section) { return section.project_id === project.id }).length
      var note = project.inbox ? "Inbox" : (project.shared ? "Shared" : "")
      var sections = count === 0 ? "" : count + (count === 1 ? " section" : " sections")
      return { name: project.name, detail: note && sections ? note + " · " + sections : (note || sections) }
    })
  } else if (sigil === "%" || sigil === "@") {
    kind = "label"
    entries = (data.labels || []).map(function(label) { return { name: label.name, detail: "" } })
  } else if (sigil === "/") {
    kind = "section"
    var project = projectBefore(text, start, data)
    if (project)
      entries = (data.sections || [])
        .filter(function(section) { return section.project_id === project.id })
        .map(function(section) { return { name: section.name, detail: project.name } })
  } else if (sigil === "+") {
    kind = "assignee"
    var shared = projectBefore(text, start, data)
    if (shared)
      entries = ((data.collaborators || {})[shared.id] || [])
        .map(function(person) { return { name: person.name, detail: person.email } })
  } else if (sigil === "!") {
    // Reminders and deadlines are Todoist Pro features; offering one to a free account only ends in a refusal.
    kind = "reminder"
    if (data.premium === true)
      entries = reminderChoices.map(function(choice) { return { name: choice, detail: "" } })
  }
  return pick(entries, query).map(function(entry) {
    return { kind: kind, label: entry.name, detail: entry.detail, insert: mention(sigil, entry.name) + " " }
  })
}

// The picker for the cursor position, or null. `soft` pickers (priority) never take Enter.
function completionAt(text, cursor, account) {
  var before = text.slice(0, cursor)
  var start = -1
  for (var i = before.length - 1; i >= 0; i--) {
    if (before[i] === "\n")
      break
    if ("#%@+!/".indexOf(before[i]) >= 0 && isSpace(before[i - 1])) {
      start = i
      break
    }
  }
  if (start >= 0) {
    var query = fold(before.slice(start + 1))
    if (query.length > maxQueryLength)
      return null
    var items = suggestionsFor(before[start], query, text, start, account)
    if (items.length === 0)
      return null
    return { kind: items[0].kind, start: start, end: cursor, query: query, soft: false, items: items }
  }

  var word = before.slice(before.search(/\S*$/))
  if (/^p$/i.test(word)) {
    return {
      kind: "priority",
      start: cursor - 1,
      end: cursor,
      query: "p",
      soft: true,
      items: priorityChoices.map(function(choice) {
        return { kind: "priority", label: choice.value, detail: choice.detail, insert: choice.value + " " }
      })
    }
  }
  return null
}

// Replace the typed trigger with the chosen entry; the cursor lands after it. The entry brings its
// own trailing space unless the text already continues with one.
function applyCompletion(text, completion, item) {
  var rest = text.slice(completion.end)
  var insert = isSpace(rest.charAt(0)) && rest !== "" ? item.insert.replace(/ $/, "") : item.insert
  return {
    text: text.slice(0, completion.start) + insert + rest,
    cursor: completion.start + insert.length + (insert === item.insert ? 0 : 1)
  }
}

// What is wrong with a recognised token, in words for the chip, or "". Silent until the account is loaded.
function chipNote(token, account) {
  var loaded = account && account.projects && account.projects.length > 0
  if (!loaded)
    return ""
  if (token.known === false)
    return "not found"
  if ((token.kind === "reminder" || token.kind === "deadline") && account.premium !== true)
    return "needs Todoist Pro"
  return ""
}

// The draft as StyledText with each recognised word in its own colour. The text field itself is drawn
// transparent and only supplies the caret and the selection, so every character must keep its width:
// spaces become &nbsp; (StyledText collapses runs of them) and overlapping tokens are skipped.
function escapeStyled(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/ /g, "&nbsp;")
}

function styledDraft(text, tokens, colorFor, baseColor) {
  var marks = tokens.slice().sort(function(a, b) { return a.start - b.start || a.end - b.end })
  var html = ""
  var at = 0
  for (var i = 0; i < marks.length; i++) {
    var mark = marks[i]
    if (mark.start < at || mark.end > text.length || mark.end <= mark.start)
      continue
    html += wrapColor(text.slice(at, mark.start), baseColor)
    html += wrapColor(text.slice(mark.start, mark.end), colorFor(mark))
    at = mark.end
  }
  return html + wrapColor(text.slice(at), baseColor)
}

function wrapColor(piece, color) {
  return piece === "" ? "" : '<font color="' + color + '">' + escapeStyled(piece) + "</font>"
}

// The one quiet line under the sentence: what was recognised, in words, in the order it was typed.
// A section follows its project after a slash; everything else is separated by a middle dot.
function metaParts(tokens, account) {
  var parts = []
  for (var i = 0; i < tokens.length; i++) {
    var token = tokens[i]
    var raw = String(token.text || "")
    var text = raw
    if (token.kind === "date")
      text = String(token.label || raw)
    else if (token.kind === "priority")
      text = "priority " + raw.slice(1)
    else if (token.kind === "reminder")
      text = "reminder " + raw.slice(1)
    else if (token.kind === "deadline")
      text = "deadline " + raw.replace(/^\{|\}$/g, "")
    else
      text = raw.slice(1)
    var previous = i > 0 ? tokens[i - 1] : null
    parts.push({
      token: token,
      kind: token.kind,
      text: text,
      note: chipNote(token, account),
      separator: previous === null ? "" : (previous.kind === "project" && token.kind === "section" ? "/" : "·")
    })
  }
  return parts
}
