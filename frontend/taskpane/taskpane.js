const BACKEND_ORIGINS = [
  "https://localhost:8000",
  "https://127.0.0.1:8000",
];
const DEFAULT_TITLE = "Current State";
const PPTX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation";
const REQUIRED_POWERPOINT_API = "1.2";

const state = {
  initialized: false,
  promptText: "",
  planResponse: null,
  clarificationQuestions: [],
};

function initialize() {
  const promptInput = document.getElementById("slidePrompt");
  const createPlanButton = document.getElementById("createPlanButton");
  const generateDeckButton = document.getElementById("generateDeckButton");
  const addSlideButton = document.getElementById("addSlideButton");
  const backToPromptButton = document.getElementById("backToPromptButton");

  createPlanButton.addEventListener("click", () => createPlan(promptInput.value));
  generateDeckButton.addEventListener("click", generateDeckFromPlan);
  addSlideButton.addEventListener("click", addSlide);
  backToPromptButton.addEventListener("click", showPromptStep);

  showPromptStep();
  setStatus("Ready");
  state.initialized = true;
}

async function createPlan(promptText) {
  const trimmedPrompt = promptText.trim();

  if (!trimmedPrompt) {
    setStatus("Enter a slide description first.", "error");
    return;
  }

  setLoading(true);
  setStatus("Creating plan...");

  try {
    const response = await postToBackend("/plan/v2", {
      title: DEFAULT_TITLE,
      content: trimmedPrompt,
    });
    await assertSuccessfulJsonResponse(response);

    state.promptText = trimmedPrompt;
    state.planResponse = await response.json();

    if (state.planResponse.needs_clarification) {
      renderClarification(state.planResponse);
      setStatus("Clarification needed", "error");
      return;
    }

    normalizeDeckSpec();
    renderPlanEditor();
    showPlanStep();
    setStatus("Plan ready for review", "success");
  } catch (error) {
    console.error("Plan creation failed", error);
    setStatus(`Plan failed: ${formatError(error)}`, "error");
  } finally {
    setLoading(false);
  }
}

async function generateDeckFromPlan() {
  if (!state.planResponse || !state.planResponse.deck_spec) {
    setStatus("Create a plan first.", "error");
    return;
  }

  normalizeDeckSpec();

  if (!state.planResponse.deck_spec.slides.length) {
    setStatus("Plan must contain at least one slide.", "error");
    return;
  }

  setLoading(true);
  setStatus("Generating deck...");

  try {
    const response = await postToBackend("/generate/v2/from-plan", {
      title: state.planResponse.title || DEFAULT_TITLE,
      content: state.planResponse.content || state.promptText,
      deck_spec: state.planResponse.deck_spec,
      preferences: {
        user_visual_preferences: buildVisualPreferences(),
      },
    });

    await assertSuccessfulPptxResponse(response);
    const blob = await response.blob();

    if (canInsertSlides()) {
      try {
        await insertPptxIntoCurrentPresentation(blob);
        setStatus("Generation Complete", "success");
      } catch (insertError) {
        console.warn("EY AI Pitch: slide insertion failed; falling back to download", insertError);
        downloadPptx(blob);
        setStatus(`Slide insertion failed (${formatError(insertError)}); PPTX downloaded`, "error");
      }
    } else {
      downloadPptx(blob);
      setStatus("Generation Complete - downloaded PPTX", "success");
    }
  } catch (error) {
    console.error("Deck generation failed", error);
    setStatus(`Generation failed: ${formatError(error)}`, "error");
  } finally {
    setLoading(false);
  }
}

async function postToBackend(path, payload) {
  let lastError;

  for (const origin of BACKEND_ORIGINS) {
    const backendUrl = `${origin}${path}`;
    try {
      console.log(`EY AI Pitch: POST ${backendUrl}`);
      return await fetch(backendUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
    } catch (error) {
      lastError = error;
      console.warn(`EY AI Pitch: request failed for ${backendUrl}`, error);
    }
  }

  throw new Error(`Network error: ${formatError(lastError)}`);
}

function renderPlanEditor() {
  const planList = document.getElementById("planList");
  const summary = document.getElementById("planSummary");
  const deckSpec = state.planResponse.deck_spec;

  planList.innerHTML = "";
  summary.textContent = `${deckSpec.presentation_type} • ${deckSpec.estimated_slide_count} slides • ${deckSpec.audience}`;

  deckSpec.slides.forEach((slide, index) => {
    const row = document.createElement("article");
    row.className = "slide-plan-row";

    const header = document.createElement("div");
    header.className = "slide-plan-header";

    const number = document.createElement("span");
    number.className = "slide-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const roleInput = document.createElement("input");
    roleInput.value = slide.slide_role || "";
    roleInput.setAttribute("aria-label", `Slide ${index + 1} role`);
    roleInput.addEventListener("input", () => {
      slide.slide_role = roleInput.value;
    });

    header.append(number, roleInput);

    const purpose = document.createElement("textarea");
    purpose.rows = 3;
    purpose.value = slide.purpose || "";
    purpose.setAttribute("aria-label", `Slide ${index + 1} purpose`);
    purpose.addEventListener("input", () => {
      slide.purpose = purpose.value;
    });

    const visualization = document.createElement("input");
    visualization.value = slide.visualization_type || "";
    visualization.setAttribute("aria-label", `Slide ${index + 1} visualization type`);
    visualization.addEventListener("input", () => {
      slide.visualization_type = visualization.value;
    });

    const variantSelect = document.createElement("select");
    variantSelect.setAttribute("aria-label", `Slide ${index + 1} visual variant`);
    const variantInfo = variantInfoForSlide(slide, index);
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = "Automatic visual";
    variantSelect.append(blank);
    variantInfo.available_variants.forEach((variant) => {
      const option = document.createElement("option");
      option.value = variant.variant_id;
      option.textContent = variant.label;
      variantSelect.append(option);
    });
    variantSelect.value = slide.visual_variant || variantInfo.recommended_variant || "";
    variantSelect.addEventListener("change", () => {
      slide.visual_variant = variantSelect.value;
    });

    const controls = document.createElement("div");
    controls.className = "row-controls";
    controls.append(
      rowButton("Up", () => moveSlide(index, -1), index === 0),
      rowButton("Down", () => moveSlide(index, 1), index === deckSpec.slides.length - 1),
      rowButton("Duplicate", () => duplicateSlide(index)),
      rowButton("Remove", () => removeSlide(index), deckSpec.slides.length === 1),
    );

    row.append(
      header,
      labeledField("Purpose", purpose),
      labeledField("Visualization", visualization),
      labeledField("Visual", variantSelect),
      controls,
    );
    planList.append(row);
  });
}

function renderClarification(planResponse) {
  const planList = document.getElementById("planList");
  const summary = document.getElementById("planSummary");
  const questions = [
    ...((planResponse.clarification_result || {}).content_questions || []),
    ...((planResponse.clarification_result || {}).visualization_questions || []),
  ];

  state.clarificationQuestions = questions;
  summary.textContent = "The planner needs more detail before generation.";
  planList.innerHTML = "";
  questions.forEach((question) => {
    const card = document.createElement("article");
    card.className = "clarification-card";

    const prompt = document.createElement("p");
    prompt.className = "clarification-question";
    prompt.textContent = question.question || question.prompt || String(question);

    const answer = document.createElement("textarea");
    answer.rows = 3;
    answer.className = "clarification-answer";
    answer.dataset.questionId = question.id || "";
    answer.placeholder = "Type your answer...";
    answer.setAttribute("aria-label", `Answer: ${prompt.textContent}`);

    const reason = document.createElement("p");
    reason.className = "clarification-reason";
    reason.textContent = question.reason || "";

    card.append(prompt, answer);
    if (reason.textContent) {
      card.append(reason);
    }
    planList.append(card);
  });
  const submit = document.createElement("button");
  submit.type = "button";
  submit.textContent = "Update Plan";
  submit.addEventListener("click", submitClarificationAnswers);
  planList.append(submit);
  showPlanStep({ allowGenerate: false });
}

async function submitClarificationAnswers() {
  const answers = Array.from(document.querySelectorAll(".clarification-answer")).map((input, index) => {
    const question = state.clarificationQuestions[index] || {};
    return {
      id: question.id || input.dataset.questionId || `question_${index + 1}`,
      question: question.question || "",
      answer: input.value.trim(),
      required: Boolean(question.required),
    };
  });

  const missingRequired = answers.filter((item) => item.required && !item.answer);
  if (missingRequired.length) {
    setStatus("Answer required clarification questions first.", "error");
    return;
  }

  const answered = answers.filter((item) => item.answer);
  if (!answered.length) {
    setStatus("Add at least one clarification answer.", "error");
    return;
  }

  const clarifiedPrompt = [
    state.promptText,
    "",
    "Clarification answers:",
    ...answered.map((item) => `- ${item.id}: ${item.answer}`),
  ].join("\n");

  await createPlan(clarifiedPrompt);
}

function labeledField(labelText, control) {
  const label = document.createElement("label");
  label.className = "plan-field";
  const span = document.createElement("span");
  span.textContent = labelText;
  label.append(span, control);
  return label;
}

function rowButton(label, handler, disabled = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "secondary-button";
  button.textContent = label;
  button.disabled = disabled;
  button.dataset.fixedDisabled = disabled ? "true" : "false";
  button.addEventListener("click", handler);
  return button;
}

function addSlide() {
  const deckSpec = state.planResponse.deck_spec;
  deckSpec.slides.push({
    slide_number: deckSpec.slides.length + 1,
    slide_role: "New Slide",
    purpose: "Describe the message this slide should communicate.",
    required_inputs: [],
    dependencies: [],
    visualization_type: "Executive Summary",
    confidence: 0.5,
    confidence_reason: "Added by user during plan review.",
  });
  normalizeDeckSpec();
  renderPlanEditor();
}

function duplicateSlide(index) {
  const deckSpec = state.planResponse.deck_spec;
  const clone = JSON.parse(JSON.stringify(deckSpec.slides[index]));
  clone.confidence_reason = "Duplicated by user during plan review.";
  deckSpec.slides.splice(index + 1, 0, clone);
  normalizeDeckSpec();
  renderPlanEditor();
}

function removeSlide(index) {
  const slides = state.planResponse.deck_spec.slides;
  if (slides.length <= 1) {
    setStatus("Plan must contain at least one slide.", "error");
    return;
  }
  slides.splice(index, 1);
  normalizeDeckSpec();
  renderPlanEditor();
}

function moveSlide(index, direction) {
  const slides = state.planResponse.deck_spec.slides;
  const target = index + direction;
  if (target < 0 || target >= slides.length) {
    return;
  }
  [slides[index], slides[target]] = [slides[target], slides[index]];
  normalizeDeckSpec();
  renderPlanEditor();
}

function normalizeDeckSpec() {
  const deckSpec = state.planResponse.deck_spec;
  deckSpec.slides.forEach((slide, index) => {
    slide.slide_number = index + 1;
    slide.required_inputs = Array.isArray(slide.required_inputs) ? slide.required_inputs : [];
    slide.dependencies = Array.isArray(slide.dependencies) ? slide.dependencies : [];
    slide.confidence = Number.isFinite(Number(slide.confidence)) ? Number(slide.confidence) : 0.75;
    slide.confidence_reason = slide.confidence_reason || "Edited during plan review.";
  });
  deckSpec.estimated_slide_count = deckSpec.slides.length;
}

function buildVisualPreferences() {
  const preferences = {};
  const slides = state.planResponse.deck_spec.slides || [];
  slides.forEach((slide, index) => {
    if (!slide.visual_variant) {
      return;
    }
    const variantInfo = variantInfoForSlide(slide, index);
    const key = variantInfo.slide_type || normalizePreferenceKey(slide.slide_role);
    preferences[key] = slide.visual_variant;
  });
  return preferences;
}

function variantInfoForSlide(slide, index) {
  const variantInfo = (state.planResponse.slide_variants || []).find(
    (item) => item.slide_number === slide.slide_number,
  ) || (state.planResponse.slide_variants || []).find(
    (item) => item.slide_role === slide.slide_role,
  );
  return variantInfo || {
    slide_number: index + 1,
    slide_role: slide.slide_role,
    slide_type: normalizePreferenceKey(slide.slide_role),
    recommended_variant: "",
    available_variants: [],
  };
}

function normalizePreferenceKey(value) {
  return String(value || "").trim().toLowerCase().replace(/[-\s]+/g, "_");
}

async function assertSuccessfulJsonResponse(response) {
  if (!response.ok) {
    const errorBody = await readErrorBody(response);
    throw new Error(`HTTP ${response.status} ${response.statusText}: ${errorBody}`);
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("application/json")) {
    throw new Error(`Unexpected response type "${contentType || "unknown"}"; expected JSON.`);
  }
}

async function assertSuccessfulPptxResponse(response) {
  if (!response.ok) {
    const errorBody = await readErrorBody(response);
    throw new Error(`HTTP ${response.status} ${response.statusText}: ${errorBody}`);
  }

  const contentType = response.headers.get("content-type") || "";

  if (!contentType.includes(PPTX_CONTENT_TYPE)) {
    throw new Error(`Unexpected response type "${contentType || "unknown"}"; expected PPTX.`);
  }
}

async function readErrorBody(response) {
  const rawBody = await response.text();

  if (!rawBody) {
    return "No error body returned by backend.";
  }

  try {
    const parsed = JSON.parse(rawBody);
    return parsed.detail || parsed.message || JSON.stringify(parsed);
  } catch (error) {
    console.warn("EY AI Pitch: error response was not JSON", error);
    return rawBody;
  }
}

function canInsertSlides() {
  return Boolean(
    window.Office &&
      window.PowerPoint &&
      Office.context &&
      Office.context.host === Office.HostType.PowerPoint &&
      Office.context.requirements &&
      Office.context.requirements.isSetSupported("PowerPointApi", REQUIRED_POWERPOINT_API)
  );
}

async function insertPptxIntoCurrentPresentation(blob) {
  const base64File = await blobToBase64(blob);

  await PowerPoint.run(async (context) => {
    context.presentation.insertSlidesFromBase64(base64File);
    await context.sync();
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onload = () => {
      const result = reader.result || "";
      const base64 = String(result).split(",")[1];

      if (!base64) {
        reject(new Error("Unable to convert generated PPTX to base64."));
        return;
      }

      resolve(base64);
    };

    reader.onerror = () => {
      reject(reader.error || new Error("Unable to read generated PPTX."));
    };

    reader.readAsDataURL(blob);
  });
}

function downloadPptx(blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = "generated_slide.pptx";
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
}

function showPromptStep() {
  document.getElementById("promptPanel").hidden = false;
  document.getElementById("planPanel").hidden = true;
}

function showPlanStep(options = {}) {
  document.getElementById("promptPanel").hidden = true;
  document.getElementById("planPanel").hidden = false;
  document.getElementById("generateDeckButton").hidden = options.allowGenerate === false;
}

function formatError(error) {
  if (!error) {
    return "Unknown error";
  }

  return error.message || String(error);
}

function setLoading(isLoading) {
  const controls = document.querySelectorAll("button, textarea, input, select");
  controls.forEach((control) => {
    control.disabled = isLoading || control.dataset.fixedDisabled === "true";
  });
}

function setStatus(message, tone) {
  const statusText = document.getElementById("statusText");

  statusText.textContent = message;
  statusText.classList.remove("success", "error");

  if (tone) {
    statusText.classList.add(tone);
  }
}

if (window.Office) {
  Office.onReady(initialize);
} else {
  initialize();
}
