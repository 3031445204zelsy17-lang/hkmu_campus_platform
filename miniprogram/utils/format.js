function pad(value) {
  return String(value).padStart(2, "0");
}

function formatDate(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value).replace("T", " ").slice(0, 16);
  }

  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function getInitial(value) {
  const text = String(value || "").trim();
  return text ? text.slice(0, 1).toUpperCase() : "H";
}

module.exports = {
  formatDate,
  getInitial,
};
