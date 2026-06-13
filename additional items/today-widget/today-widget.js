const slides = Array.from(document.querySelectorAll(".today-slide"));
let activeIndex = 0;

function renderDots() {
  slides.forEach((slide) => {
    const dots = slide.querySelector(".today-dots");
    dots.innerHTML = "";

    slides.forEach((_, index) => {
      const dot = document.createElement("button");
      dot.className = `today-dot ${index === activeIndex ? "active" : ""}`;
      dot.type = "button";
      dot.setAttribute("aria-label", `Show slide ${index + 1}`);

      dot.addEventListener("click", () => {
        activeIndex = index;
        renderSlides();
      });

      dots.appendChild(dot);
    });
  });
}

function renderSlides() {
  slides.forEach((slide, index) => {
    slide.classList.toggle("active", index === activeIndex);
  });

  renderDots();
}

setInterval(() => {
  activeIndex = (activeIndex + 1) % slides.length;
  renderSlides();
}, 4200);

renderSlides();
