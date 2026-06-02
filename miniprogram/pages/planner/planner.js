const { syncTabBar } = require("../../utils/tabbar");
const { getLocale, getTexts } = require("../../utils/i18n");

const COURSE_ITEMS = [
  {
    className: "mini-pill green",
    code: "COMP S350",
    name: "Software Engineering",
    statusKey: "active",
  },
  {
    className: "mini-pill orange",
    code: "BUS B220",
    name: "Digital Business",
    statusKey: "pending",
  },
  {
    className: "mini-pill",
    code: "GEN G200",
    name: "General Education",
    statusKey: "planned",
  },
];

function buildCourses(text = getTexts("planner")) {
  return COURSE_ITEMS.map((item) => Object.assign({}, item, {
    status: text.statuses[item.statusKey],
  }));
}

Page({
  data: {
    courses: buildCourses(),
    locale: getLocale(),
    text: getTexts("planner"),
  },

  onShow() {
    this.applyLocale(getLocale());
    syncTabBar(this, 2);
  },

  handleLanguageChange(event) {
    this.applyLocale(event.detail.locale);
  },

  applyLocale(locale = getLocale()) {
    const text = getTexts("planner", locale);

    this.setData({
      courses: buildCourses(text),
      locale,
      text,
    });

    syncTabBar(this, 2);
  },
});
