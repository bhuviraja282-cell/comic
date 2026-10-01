const form = document.querySelector("#comic-form");
const promptField = document.querySelector("#story-prompt");
const countLabel = document.querySelector("#character-count");
const grid = document.querySelector("#panel-grid");
const toast = document.querySelector("#toast");
let currentComic = null;
let selectedTone = "Adventurous";
let toastTimer;

function icons() {
  window.lucide?.createIcons();
}

function setLoadingState(isLoading) {
  const button = form.querySelector(".generate-button");
  const buttonText = button.querySelector("span");
  button.disabled = isLoading;
  form.classList.toggle("is-loading", isLoading);
  buttonText.textContent = isLoading ? "Building your story..." : "Make my comic";
  icons();
}

function applyPromptPreset(promptText) {
  promptField.value = promptText.trim();
  countLabel.textContent = `${promptField.value.length} / 1000`;
  promptField.focus();
}

function renderComic(comic, mode = "AI-GENERATED COMIC") {
  currentComic = comic;
  grid.classList.remove("is-empty");
  document.querySelector("#comic-title").textContent = comic.title;
  document.querySelector("#panel-count").textContent = `${comic.panels.length} PANELS`;
  document.querySelector("#canvas-mode").textContent = mode;
  document.querySelector("#download-button").disabled = false;
  grid.replaceChildren(...comic.panels.map((panel, index) => {
    const card = document.createElement("article");
    card.className = "comic-panel";
    const imageBox = document.createElement("div");
    imageBox.className = "panel-image";
    const number = document.createElement("span");
    number.className = "panel-number";
    number.textContent = String(index + 1).padStart(2, "0");
    imageBox.append(number);
    if (panel.image) {
      const image = document.createElement("img");
      image.src = panel.image;
      image.alt = panel.image_prompt || `Illustration for ${panel.title}`;
      image.loading = index > 1 ? "lazy" : "eager";
      image.referrerPolicy = "no-referrer";
      imageBox.prepend(image);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "panel-art-placeholder";
      const artIcon = document.createElement("i");
      artIcon.dataset.lucide = panel.image_error ? "image-off" : "image";
      const label = document.createElement("span");
      label.textContent = panel.image_error ? "Illustration unavailable" : "Illustration pending";
      placeholder.append(artIcon, label);
      imageBox.prepend(placeholder);
    }
    const copy = document.createElement("div");
    copy.className = "panel-copy";
    const heading = document.createElement("h3");
    heading.textContent = panel.title;
    const narration = document.createElement("p");
    narration.textContent = panel.narration;
    copy.append(heading, narration);
    card.append(imageBox, copy);
    return card;
  }));
  icons();
}

function clearPreview() {
  currentComic = null;
  grid.classList.add("is-empty");
  grid.replaceChildren();
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.innerHTML = '<i data-lucide="book-open-check"></i><span>Your next story starts with an idea only you could dream up.</span>';
  grid.append(empty);
  document.querySelector("#comic-title").textContent = "A STORY WAITING TO BE TOLD";
  document.querySelector("#panel-count").textContent = "0 PANELS";
  document.querySelector("#canvas-mode").textContent = "READY WHEN YOU ARE";
  document.querySelector("#download-button").disabled = true;
  icons();
}

function notify(message) {
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3400);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fields = {
    prompt: promptField.value.trim(),
    character: form.elements.character.value,
    setting: form.elements.setting.value,
    tone: selectedTone,
    style: form.elements.style.value,
  };
  if (fields.prompt.length < 8) {
    notify("Give your story idea a few more details first.");
    promptField.focus();
    return;
  }

  setLoadingState(true);
  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const message = typeof result.detail === "string" ? result.detail : "Comic generation failed. Please try again.";
      if (response.status === 503) throw new Error("Gemini API key required. Add GEMINI_API_KEY to .env and restart ComicCraft.");
      throw new Error(message);
    }
    renderComic(result);
    notify(result.image_warning || "Your new comic is ready.");
  } catch (error) {
    notify(error.message || "Could not reach ComicCraft. Check that the server is running.");
  } finally {
    setLoadingState(false);
    icons();
  }
});

document.querySelectorAll(".tone-choices .choice").forEach((button) => {
  button.addEventListener("click", () => {
    selectedTone = button.dataset.tone;
    document.querySelectorAll(".tone-choices .choice").forEach((choice) => {
      choice.classList.toggle("is-selected", choice === button);
      choice.setAttribute("aria-pressed", String(choice === button));
    });
  });
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    document.querySelectorAll(".chip").forEach((btn) => btn.classList.toggle("is-selected", btn === chip));
    applyPromptPreset(chip.dataset.prompt);
  });
});

promptField.addEventListener("input", () => {
  countLabel.textContent = `${promptField.value.length} / 1000`;
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.classList.toggle("is-selected", chip.dataset.prompt.trim() === promptField.value.trim());
  });
});

document.querySelector("#refresh-button").addEventListener("click", () => {
  clearPreview();
});

document.querySelector("#download-button").addEventListener("click", async () => {
  if (!currentComic) return;
  try {
    const response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: currentComic.title, panels: currentComic.panels }),
    });
    if (!response.ok) throw new Error("The PDF could not be created.");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(await response.blob());
    link.download = `${currentComic.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "comiccraft-story"}.pdf`;
    link.click();
    URL.revokeObjectURL(link.href);
    notify("Your comic PDF is downloading.");
  } catch (error) {
    notify(error.message || "Start the ComicCraft server to export a PDF.");
  }
});

async function updateStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    const provider = document.querySelector("#provider-status");
    const note = document.querySelector("#engine-note-text");
    if (status.gemini) {
      provider.textContent = status.images ? "GEMINI + IMAGES" : "GEMINI READY";
      note.textContent = status.image_provider === "Hugging Face"
        ? "Stories and illustrations use Gemini and Hugging Face."
        : `Gemini stories and ${status.image_model} illustrations; image quota may require billing.`;
    } else {
      provider.textContent = "ADD GEMINI KEY";
      note.textContent = "Add GEMINI_API_KEY to .env to create comics.";
    }
  } catch { /* The prompt canvas remains usable without the generation API. */ }
}

countLabel.textContent = `${promptField.value.length} / 1000`;
clearPreview();
updateStatus();