const BACKEND_URLS = [
  "https://localhost:8000/generate/v2",
  "https://127.0.0.1:8000/generate/v2",
];
const DEFAULT_TITLE = "Current State";
const PPTX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation";
const REQUIRED_POWERPOINT_API = "1.2";

const state = {
  initialized: false,
};

function initialize() {
  const promptInput = document.getElementById("slidePrompt");
  const generateButton = document.getElementById("generateButton");

  generateButton.addEventListener("click", () => generateSlide(promptInput.value));
  setStatus("Ready");
  state.initialized = true;
}

async function generateSlide(promptText) {
  const trimmedPrompt = promptText.trim();

  if (!trimmedPrompt) {
    setStatus("Enter a slide description first.", "error");
    return;
  }

  setLoading(true);
  setStatus("Generating...");

  try {
    console.log("EY AI Pitch: request started");

    const response = await postToBackend({
      title: DEFAULT_TITLE,
      content: trimmedPrompt,
    });

    console.log("EY AI Pitch: response received", {
      status: response.status,
      contentType: response.headers.get("content-type"),
    });

    await assertSuccessfulPptxResponse(response);

    const blob = await response.blob();
    console.log("EY AI Pitch: PPTX received", { bytes: blob.size });

    if (canInsertSlides()) {
      console.log("EY AI Pitch: slide insertion started");
      try {
        await insertPptxIntoCurrentPresentation(blob);
        console.log("EY AI Pitch: slide insertion complete");
        setStatus("Generation Complete", "success");
      } catch (insertError) {
        console.warn("EY AI Pitch: slide insertion failed; falling back to download", insertError);
        downloadPptx(blob);
        setStatus(`Slide insertion failed (${formatError(insertError)}); PPTX downloaded`, "error");
      }
    } else {
      console.warn("EY AI Pitch: PowerPointApi 1.2 unavailable; falling back to download");
      downloadPptx(blob);
      setStatus("Generation Complete - downloaded PPTX", "success");
    }
  } catch (error) {
    console.error("Slide generation failed", error);
    setStatus(`Generation failed: ${formatError(error)}`, "error");
  } finally {
    setLoading(false);
  }
}

async function postToBackend(payload) {
  let lastError;

  for (const backendUrl of BACKEND_URLS) {
    try {
      console.log(`Generating using endpoint: ${backendUrl}`);

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
    // Some Office.js runtimes (especially on Mac) reject the options object or
    // the InsertSlideFormatting value with InvalidArgument. Calling the method
    // without options uses the runtime default and is the most compatible path.
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

  console.log("EY AI Pitch: download started", { bytes: blob.size });

  link.href = url;
  link.download = "generated_slide.pptx";
  document.body.appendChild(link);
  link.click();
  link.remove();

  URL.revokeObjectURL(url);
}

function formatError(error) {
  if (!error) {
    return "Unknown error";
  }

  return error.message || String(error);
}

function setLoading(isLoading) {
  const generateButton = document.getElementById("generateButton");
  const promptInput = document.getElementById("slidePrompt");

  generateButton.disabled = isLoading;
  promptInput.disabled = isLoading;
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
