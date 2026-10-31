
const EDITOR_API = `http://${location.hostname}:5000/api`;

const params = new URLSearchParams(location.search);
const topicId = params.get("id");
const subjectId = params.get("subject");

const titleInput = document.getElementById("lesson-title");
const contentInput = document.getElementById("lesson-content");
const descriptionInput = document.getElementById("lesson-description");
const summaryInput = document.getElementById("lesson-summary");
const slidesContainer = document.getElementById("slides");
const message = document.getElementById("editor-message");
const fileInput = document.getElementById("presentation-file");
const uploadForm = document.getElementById("upload-form");

let slides = [];
let presentations = [];

async function request(path, options = {}) {
  const response = await fetch(EDITOR_API + path, {
    credentials: "include",
    ...options,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.error || `Request failed (${response.status})`);
  }

  return data;
}

function say(text, error = false) {
  if (!message) return;
  message.textContent = text;
  message.style.color = error ? "#b91c1c" : "#166534";
}

function renumberSlides() {
  [...slidesContainer.querySelectorAll(".slide-card")].forEach(
    (card, index) => {
      card.querySelector("h3").textContent = `Slide ${index + 1}`;
    }
  );

  const empty = document.getElementById("slides-empty");
  if (empty) empty.hidden = slidesContainer.children.length > 0;
}

function addSlide(slide = {}) {
  const card = document.createElement("article");
  card.className = "slide-card";

  const heading = document.createElement("h3");
  heading.textContent = "New slide";

  const title = document.createElement("input");
  title.type = "text";
  title.placeholder = "Slide title";
  title.value = slide.title || "";
  title.maxLength = 300;
  title.className = "slide-title";
  title.setAttribute("aria-label", "Slide title");

  const text = document.createElement("textarea");
  text.placeholder = "Slide text";
  text.rows = 5;
  text.maxLength = 10000;
  text.value = slide.text || "";
  text.className = "slide-text";
  text.setAttribute("aria-label", "Slide text");

  const image = document.createElement("input");
  image.type = "url";
  image.placeholder = "Optional image URL";
  image.value = slide.image || "";
  image.className = "slide-image";
  image.setAttribute("aria-label", "Optional slide image URL");

  const controls = document.createElement("div");
  controls.className = "slide-controls";

  const up = document.createElement("button");
  up.type = "button";
  up.textContent = "Move up";
  up.addEventListener("click", () => {
    const previous = card.previousElementSibling;
    if (previous) {
      slidesContainer.insertBefore(card, previous);
      renumberSlides();
    }
  });

  const down = document.createElement("button");
  down.type = "button";
  down.textContent = "Move down";
  down.addEventListener("click", () => {
    const next = card.nextElementSibling;
    if (next) {
      slidesContainer.insertBefore(next, card);
      renumberSlides();
    }
  });

  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "Delete";
  remove.addEventListener("click", () => {
    card.remove();
    renumberSlides();
  });

  controls.append(up, down, remove);
  card.append(heading, title, text, image, controls);
  slidesContainer.append(card);

  renumberSlides();
}

function collectSlides() {
  return [...slidesContainer.querySelectorAll(".slide-card")].map((card) => ({
    title: card.querySelector(".slide-title").value.trim(),
    text: card.querySelector(".slide-text").value,
    image: card.querySelector(".slide-image").value.trim(),
  }));
}

function renderPresentations() {
  const list = document.getElementById("presentation-list");
  const empty = document.getElementById("presentation-empty");

  list.replaceChildren();

  presentations.forEach((file) => {
    const item = document.createElement("li");
    const link = document.createElement("a");

    link.href = EDITOR_API + file.url.replace(/^\/api/, "");
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = file.name || "Presentation";
    item.append(link);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";

    remove.addEventListener("click", async () => {
      if (!await confirmDeletion(`Remove "${file.name}"?`)) return;

      try {
        await request(
          `/topics/${encodeURIComponent(topicId)}/presentations/${encodeURIComponent(file.id)}`,
          { method: "DELETE" }
        );

        presentations = presentations.filter((p) => p.id !== file.id);
        renderPresentations();
        say("Presentation removed.");
      } catch (error) {
        say(error.message, true);
      }
    });

    item.append(" ", remove);
    list.append(item);
  });

  if (empty) empty.hidden = presentations.length > 0;
}

async function loadLesson() {
  if (!topicId || !subjectId) {
    say("Missing topic or subject ID. Open this page from the Topics page.", true);
    return;
  }

  try {
    const data = await request(`/topics/${encodeURIComponent(topicId)}`);
    const topic = data.topic;

    if (!topic) throw new Error("Topic not found.");

    titleInput.value = topic.title || "";
    contentInput.innerHTML = topic.content || "";
    descriptionInput.value = topic.description || "";
    summaryInput.value = topic.summary || "";

    slides = Array.isArray(topic.slides) ? topic.slides : [];
    presentations = Array.isArray(topic.presentations)
      ? topic.presentations
      : [];

    slidesContainer.replaceChildren();
    slides.forEach((slide) => addSlide(slide));

    renderPresentations();
    renumberSlides();

    document.getElementById("back-link").href =
      `toc.html?subject=${encodeURIComponent(subjectId)}`;

    document.getElementById("preview-link").href =
      `topic-view.html?id=${encodeURIComponent(topicId)}&subject=${encodeURIComponent(subjectId)}`;

    say("Lesson loaded.");
  } catch (error) {
    say(`Could not load lesson: ${error.message}`, true);
    console.error(error);
  }
}

document.querySelectorAll("[data-command]").forEach((button) => {
  button.addEventListener("click", () => {
    contentInput.focus();

    try {
      document.execCommand(
        button.dataset.command,
        false,
        button.dataset.value || null
      );
    } catch {
      say("This formatting option is unavailable in your browser.", true);
    }
  });
});

document.getElementById("add-slide").addEventListener("click", () => {
  addSlide();
  say("Slide added.");
});

document.getElementById("save-lesson").addEventListener("click", async () => {
  if (!topicId) {
    say("Missing topic ID. Open a topic from the Topics page first.", true);
    return;
  }

  const title = titleInput.value.trim();

  if (!title) {
    say("Enter a topic title.", true);
    titleInput.focus();
    return;
  }

  const saveButton = document.getElementById("save-lesson");
  saveButton.disabled = true;

  try {
    const result = await request(`/topics/${encodeURIComponent(topicId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        description: descriptionInput.value.trim(),
        content: contentInput.innerHTML,
        summary: summaryInput.value,
        slides: collectSlides(),
      }),
    });

    if (!result.ok || !result.topic) {
      throw new Error("The server did not confirm the saved lesson.");
    }

    say("Lesson saved successfully.");
  } catch (error) {
    say(`Could not save lesson: ${error.message}`, true);
    console.error("Save failed:", error);
  } finally {
    saveButton.disabled = false;
  }
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!topicId) {
    say("Missing topic ID.", true);
    return;
  }

  const file = fileInput.files[0];

  if (!file) {
    say("Choose a presentation file first.", true);
    return;
  }

  if (!/\.(pdf|ppt|pptx)$/i.test(file.name)) {
    say("Only PDF, PPT, and PPTX files are allowed.", true);
    return;
  }

  if (file.size > 25 * 1024 * 1024) {
    say("The file must be 25 MB or smaller.", true);
    return;
  }

  const uploadButton = uploadForm.querySelector('button[type="submit"]');
  uploadButton.disabled = true;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const data = await request(
      `/topics/${encodeURIComponent(topicId)}/presentations`,
      { method: "POST", body: formData }
    );

    if (data.presentation) {
      presentations.push(data.presentation);
      renderPresentations();
    }

    fileInput.value = "";
    say("Presentation uploaded successfully.");
  } catch (error) {
    say(`Upload failed: ${error.message}`, true);
    console.error(error);
  } finally {
    uploadButton.disabled = false;
  }
});

document.getElementById("generate-summary").addEventListener("click", () => {
  const temporary = document.createElement("div");
  temporary.innerHTML = contentInput.innerHTML;

  const text = (temporary.textContent || "").replace(/\s+/g, " ").trim();

  if (!text) {
    say("Add lesson content before generating a summary.", true);
    contentInput.focus();
    return;
  }

  const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [];
  const keywords = text.match(/\b[A-Za-z][A-Za-z0-9-]{5,}\b/g) || [];
  const uniqueKeywords = [
    ...new Set(keywords.map((word) => word.toLowerCase())),
  ];

  summaryInput.value = [
    "Lesson overview",
    ...sentences.slice(0, 3).map((sentence) => sentence.trim()),
    "",
    "Key terms",
    uniqueKeywords.slice(0, 8).join(", ") ||
      "Review the main lesson concepts.",
  ].join("\n");

  say("Summary draft generated. Review it before saving.");
});

loadLesson();
