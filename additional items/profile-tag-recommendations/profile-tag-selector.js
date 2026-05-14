/*
Prototype frontend snippet for categorized profile tags and recommendations.

Suggested integration file:
- frontend/js/pages/profile.js
*/

let recommendations = [];

const TAG_CATEGORIES = [
  {
    key: "interests",
    label: "Interests",
    helper: "Choose topics you like talking about.",
    options: ["AI", "Design", "Badminton", "Gaming", "Finance", "Career", "Music", "Volunteering"],
  },
  {
    key: "current_courses",
    label: "Current courses",
    helper: "Pick courses you are taking now.",
    options: ["COMP1080SEF", "IT1020SEF", "STAT2520SEF", "COMP3500SEF", "COMP4820SEF", "DSAI Project"],
  },
  {
    key: "partner_types",
    label: "Looking for",
    helper: "Tell others what kind of connection you want.",
    options: ["Study buddy", "Project teammate", "Coffee chat", "Event buddy", "Club member"],
  },
];

function SocialTags(user) {
  const groups = [
    { label: "Interests", values: user.interests || [] },
    { label: "Courses", values: user.current_courses || [] },
    { label: "Looking for", values: user.partner_types || [] },
  ].filter((group) => group.values.length);

  if (!groups.length) return null;

  const wrap = document.createElement("div");
  wrap.className = "profile-social-tags";
  groups.forEach((group) => {
    const row = document.createElement("div");
    row.className = "profile-tag-row";
    const label = document.createElement("span");
    label.className = "profile-tag-label";
    label.textContent = group.label;
    row.appendChild(label);
    group.values.forEach((value) => {
      const chip = document.createElement("span");
      chip.className = "profile-tag-chip";
      chip.textContent = value;
      row.appendChild(chip);
    });
    wrap.appendChild(row);
  });
  return wrap;
}

function TagPicker(user) {
  const wrap = document.createElement("div");
  wrap.className = "profile-tag-picker";

  TAG_CATEGORIES.forEach((category) => {
    const group = document.createElement("fieldset");
    group.className = "tag-picker-group";

    const legend = document.createElement("legend");
    legend.textContent = category.label;
    group.appendChild(legend);

    const helper = document.createElement("p");
    helper.textContent = category.helper;
    group.appendChild(helper);

    const selected = new Set((user[category.key] || []).map((tag) => tag.toLowerCase()));
    const options = document.createElement("div");
    options.className = "tag-picker-options";

    category.options.forEach((option) => {
      const id = `tag-${category.key}-${option.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`;
      const label = document.createElement("label");
      label.className = "tag-option";
      label.setAttribute("for", id);

      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = id;
      input.name = category.key;
      input.value = option;
      input.checked = selected.has(option.toLowerCase());
      label.appendChild(input);

      const span = document.createElement("span");
      span.textContent = option;
      label.appendChild(span);
      options.appendChild(label);
    });

    group.appendChild(options);
    wrap.appendChild(group);
  });

  return wrap;
}

function selectedTags(form, name) {
  return Array.from(form.querySelectorAll(`input[name="${name}"]:checked`))
    .map((input) => input.value)
    .slice(0, 12);
}

async function loadRecommendations(api) {
  try {
    recommendations = await api.get("/users/recommendations/me?limit=6");
  } catch {
    recommendations = [];
  }
  return recommendations;
}

function RecommendationsPanel() {
  const section = document.createElement("section");
  section.className = "recommendations-panel";

  const header = document.createElement("div");
  header.className = "recommendations-header";
  const title = document.createElement("h3");
  title.textContent = "Recommended classmates";
  header.appendChild(title);
  const hint = document.createElement("p");
  hint.textContent = "Matched by shared courses, goals, and interests.";
  header.appendChild(hint);
  section.appendChild(header);

  if (!recommendations.length) {
    const empty = document.createElement("div");
    empty.className = "recommendations-empty";
    empty.textContent = "Select tags in Edit Profile to get recommendations.";
    section.appendChild(empty);
    return section;
  }

  const list = document.createElement("div");
  list.className = "recommendations-list";
  recommendations.forEach((person) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "recommendation-card";
    card.addEventListener("click", () => { location.hash = `#/profile/${person.id}`; });

    const top = document.createElement("div");
    top.className = "recommendation-top";
    const name = document.createElement("strong");
    name.textContent = person.nickname || person.username;
    top.appendChild(name);
    const score = document.createElement("span");
    score.textContent = `${person.match_score} match`;
    top.appendChild(score);
    card.appendChild(top);

    const chips = document.createElement("div");
    chips.className = "recommendation-tags";
    const matched = [
      ...(person.matched_tags?.current_courses || []),
      ...(person.matched_tags?.partner_types || []),
      ...(person.matched_tags?.interests || []),
    ].slice(0, 6);
    matched.forEach((tag) => {
      const chip = document.createElement("span");
      chip.textContent = tag;
      chips.appendChild(chip);
    });
    card.appendChild(chips);
    list.appendChild(card);
  });

  section.appendChild(list);
  return section;
}
